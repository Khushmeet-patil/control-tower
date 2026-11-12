import { mountHierarchyPage } from './hierarchy-page.js';

mountHierarchyPage({
  navKey: 'organisation',
  title: 'Organisation',
  subtitle: 'The administrative hierarchy: divisions, departments and teams, and who heads each one.',
  endpoint: '/units',
  singular: 'unit',
  plural: 'units',
  childLabel: 'sub-unit',
  childPlural: 'sub-units',
  hasTypes: true,
  leaderField: 'head_id',
  leaderKey: 'head',
  leaderLabel: 'Head',
  memberFilter: 'unit_id',
  viewPermission: 'org.view',
  managePermission: 'org.manage',
});
