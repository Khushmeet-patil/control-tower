/**
 * Create and edit work items.
 *
 *   openNewWorkItem({ parent, onDone })     → asks "what are you adding?" (item types), then the form
 *   openWorkItemEditor({ item, onDone })    → edit; people who may only update progress see the other
 *                                              fields read-only (item.permissions.editable_fields)
 *
 * Children inherit the parent's unit, priority, category and owners on the server when left empty.
 * Choosing a different accountable owner than the parent's, or handing over an existing item,
 * needs a reason, which goes to the audit log.
 */
import { api } from '../core/api.js';
import { customFields, defaultLookupValue, lookupOptions, lookupValue, lookupValues, term } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { customFormFields, withCustomValues } from './custom-fields.js';
import { openFormModal } from './form-builder.js';
import { openModal } from './modal.js';
import { treeOptions } from './tree.js';
import { showToast } from './toast.js';

let orgCache = null;
function loadOrg() {
  if (!orgCache) {
    orgCache = Promise.all([
      api.get('/units').then((d) => d.items).catch(() => []),
      api.get('/functions').then((d) => d.items).catch(() => []),
    ]).then(([units, functions]) => ({ unitOptions: treeOptions(units), functionOptions: treeOptions(functions) }));
  }
  return orgCache;
}

const typeCode = (id) => lookupValue(id)?.code;
const isAction = (typeId) => typeCode(typeId) === 'action';
const isLarge = (typeId) => ['programme', 'project'].includes(typeCode(typeId));

/** Ask which kind of item to add, then open the form. */
export function openNewWorkItem({ parent = null, onDone } = {}) {
  const types = lookupValues('item_type');
  const modal = openModal({
    title: parent ? `Add under ${parent.code}` : `New ${term('work_item', { fallback: 'work item' }).toLowerCase()}`,
    body: el('div', { class: 'ct-stack' },
      el('p', { class: 'ct-muted ct-small' }, parent
        ? `It will inherit ${parent.code}'s unit, priority and owners unless you change them.`
        : 'What are you adding?'),
      el('div', { class: 'ct-type-grid' }, types.map((t) => el('button', {
        class: 'ct-btn ct-type-grid__btn', type: 'button',
        onClick: () => { modal.close(); openWorkItemEditor({ parent, itemTypeId: t.id, onDone }); },
      }, el('span', { class: 'ct-dot', style: { background: t.color } }), t.label)))),
    actions: [{ label: 'Cancel' }],
  });
}

/**
 * The work item form's field definitions (also used by form tools, which show a subset of them).
 * Fields the user may not change on `item` come back disabled.
 */
export async function workItemFormFields({ item = null, parent = null, itemTypeId = null } = {}) {
  const { unitOptions, functionOptions } = await loadOrg();
  const typeId = item ? item.item_type_id : itemTypeId;
  const editable = item?.permissions?.editable_fields; // null → everything; [] → nothing
  const locked = (key) => Boolean(item && editable && !editable.includes(key));
  const inheritHelp = parent ? 'Leave empty to use the parent\'s.' : null;

  return [
    { key: 'title', label: 'Title', required: true, full: true, maxlength: 300 },
    item ? { key: 'item_type_id', label: 'Type', type: 'select', options: lookupOptions('item_type', typeId), required: true } : null,
    { key: 'status_id', label: 'Status', type: 'select', options: lookupOptions('status', item?.status_id), default: item ? null : defaultLookupValue('status') },
    { key: 'priority_id', label: 'Priority', type: 'select', options: lookupOptions('priority', item?.priority_id), help: inheritHelp },
    isAction(typeId) ? { key: 'action_type_id', label: 'Action type', type: 'select', options: lookupOptions('action_type', item?.action_type_id), default: item ? null : defaultLookupValue('action_type') } : null,
    isAction(typeId) ? { key: 'severity_id', label: 'Severity', type: 'select', options: lookupOptions('severity', item?.severity_id) } : null,
    { key: 'category_id', label: 'Category', type: 'select', options: lookupOptions('category', item?.category_id), help: inheritHelp },
    { key: 'unit_id', label: 'Assigned to unit', type: 'select', options: unitOptions, help: parent ? 'The parent\'s unit or one below it. Leave empty to use the parent\'s.' : 'The team or unit that delivers this work.' },
    { key: 'function_id', label: 'Function', type: 'select', options: functionOptions, help: 'Optional: the discipline that leads this work.' },
    { key: 'accountable_id', label: 'Accountable owner', type: 'person', value: item?.accountable || null,
      help: item ? 'Changing this is a handover and needs a reason.' : parent ? 'Leave empty to inherit the parent\'s. A different owner needs a reason.' : 'Leave empty to be accountable yourself.' },
    { key: 'responsible_ids', label: 'Responsible owners', type: 'people', value: item?.responsibles || [],
      help: item ? 'At least one.' : parent ? 'Leave empty to inherit the parent\'s.' : 'Leave empty to use the accountable owner.' },
    { key: 'planned_start', label: isAction(typeId) ? 'Raised on' : 'Planned start', type: 'date' },
    { key: 'planned_end', label: isAction(typeId) ? 'Due date' : 'Planned finish (target)', type: 'date' },
    { key: 'actual_start', label: 'Actual start', type: 'date' },
    { key: 'actual_end', label: 'Actual finish', type: 'date' },
    { key: 'progress_manual', label: 'Progress % (only used while it has no child items)', type: 'number' },
    { key: 'weight', label: 'Weight in the parent\'s progress', type: 'number', help: 'Default 1. A weight of 3 counts three times as much as its siblings.' },
    { key: 'evidence_url', label: 'Evidence / deliverable link', type: 'url', placeholder: 'https://' },
    { key: 'description', label: 'Description', type: 'textarea' },
    isLarge(typeId) ? { key: 'objective', label: 'Business objective', type: 'textarea' } : null,
    isLarge(typeId) || isAction(typeId) ? { key: 'risks', label: isAction(typeId) ? 'Impact' : 'Key risks', type: 'textarea' } : null,
    { key: 'remarks', label: 'Remarks', type: 'textarea' },
    ...customFormFields('work_item', item).filter((f) => {
      const def = customFields('work_item').find((c) => `custom_fields.${c.code}` === f.key);
      return !def?.item_type_ids?.length || def.item_type_ids.includes(typeId);
    }),
    item || parent ? { key: 'reason', label: item ? 'Reason for change' : 'Reason (needed if the accountable owner differs from the parent\'s)', full: true, help: 'Saved in the audit log.' } : null,
  ].filter(Boolean).map((f) => (f.key !== 'reason' && locked(f.key) ? { ...f, disabled: true, required: false } : f));
}

export async function openWorkItemEditor({ item = null, parent = null, itemTypeId = null, onDone } = {}) {
  const fields = await workItemFormFields({ item, parent, itemTypeId });
  const typeId = item ? item.item_type_id : itemTypeId;
  const editable = item?.permissions?.editable_fields;
  const typeLabel = lookupValue(typeId)?.label || 'item';
  openFormModal({
    title: item ? `${item.code} · ${item.title}` : `New ${typeLabel.toLowerCase()}${parent ? ` under ${parent.code}` : ''}`,
    intro: item && editable?.length ? 'You can update the status, actual dates, progress, evidence and remarks of this item. Other fields are managed by its owners.' : null,
    fields,
    values: item || {},
    submitLabel: item ? 'Save changes' : `Add ${typeLabel.toLowerCase()}`,
    onSubmit: (raw) => {
      let values = withCustomValues(raw);
      if (item && editable) {
        values = Object.fromEntries(Object.entries(values).filter(([k]) => editable.includes(k) || k === 'reason'));
      }
      if (!item) {
        values.item_type_id = typeId;
        if (parent) values.parent_id = parent.id;
        // Empty owner fields mean "inherit / default" on create.
        if (!values.responsible_ids?.length) delete values.responsible_ids;
        for (const key of Object.keys(values)) if (values[key] === null) delete values[key];
        return api.post('/work-items', values);
      }
      return api.patch(`/work-items/${item.id}`, { ...values, version: item.version });
    },
    onDone: (saved) => {
      showToast(item ? 'Changes saved' : `${saved.code} added`, 'success');
      onDone?.(saved);
    },
  });
}
