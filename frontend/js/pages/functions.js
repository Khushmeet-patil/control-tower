import { mountHierarchyPage } from './hierarchy-page.js';

mountHierarchyPage({
  navKey: 'functions',
  title: 'Functions',
  subtitle: 'The functional hierarchy: disciplines such as Development or QA, and their functional leads.',
  endpoint: '/functions',
  singular: 'function',
  plural: 'functions',
  childLabel: 'sub-function',
  childPlural: 'sub-functions',
  hasTypes: false,
  leaderField: 'lead_id',
  leaderKey: 'lead',
  leaderLabel: 'Functional lead',
  memberFilter: 'function_id',
  viewPermission: 'functions.view',
  managePermission: 'functions.manage',
});
