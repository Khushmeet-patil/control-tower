/**
 * Adoption pipeline (the prototype's Dev → Test → Accepted → Trained → Rollout → Adopted).
 * The stages are the "Adoption stage" lookup list, so admins rename, reorder or add them.
 *   adoptionStages()                              → active stages in order
 *   createStageToggle(item, stage, { onSaved })   → checkbox that saves the change (audited)
 *   createAdoptionChecklist(item, { editable, onSaved }) → the item page's checklist + evidence
 */
import { api } from '../core/api.js';
import { lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { openFormModal } from './form-builder.js';
import { showError } from './toast.js';
import { safeLink } from './work-table.js';

export function adoptionStages() {
  return lookupValues('adoption_stage');
}

export async function saveAdoption(item, changes) {
  return api.patch(`/work-items/${item.id}`, { ...changes, version: item.version, reason: 'Adoption updated' });
}

export function createStageToggle(item, stage, { onSaved, disabled = false } = {}) {
  const reached = (item.adoption_stage_ids || []).includes(stage.id);
  const box = el('input', { type: 'checkbox', checked: reached, disabled, 'aria-label': `${stage.label}: ${item.code}`,
    onChange: async () => {
      box.disabled = true;
      const ids = new Set(item.adoption_stage_ids || []);
      if (box.checked) ids.add(stage.id); else ids.delete(stage.id);
      try {
        onSaved?.(await saveAdoption(item, { adoption_stage_ids: [...ids] }));
      } catch (err) {
        box.checked = !box.checked;
        box.disabled = false;
        showError(err);
      }
    } });
  return box;
}

export function editEvidence(item, { onSaved } = {}) {
  openFormModal({
    title: `Adoption evidence · ${item.code}`, wide: false,
    fields: [{ key: 'adoption_evidence', label: 'Evidence that people use it (link or short note)', type: 'text' }],
    values: { adoption_evidence: item.adoption_evidence },
    onSubmit: (v) => saveAdoption(item, { adoption_evidence: v.adoption_evidence || null }),
    onDone: onSaved,
  });
}

export function evidenceNode(text) {
  if (!text) return el('span', { class: 'ct-muted' }, '—');
  return /^https?:\/\//i.test(text) ? safeLink(text, 'Open') : el('span', {}, text);
}

export function createAdoptionChecklist(item, { editable = false, onSaved } = {}) {
  const stages = adoptionStages();
  if (!stages.length) return el('p', { class: 'ct-muted ct-small' }, 'No adoption stages are set up.');
  return el('div', { class: 'ct-stack', style: { gap: '8px' } },
    el('div', { class: 'ct-adoption' }, stages.map((s) => el('label', { class: 'ct-checkbox' },
      createStageToggle(item, s, { onSaved, disabled: !editable }), s.label))),
    el('div', { class: 'ct-small' }, el('strong', {}, 'Evidence: '), evidenceNode(item.adoption_evidence),
      editable ? [' ', el('button', { class: 'ct-link-button ct-small', type: 'button', onClick: () => editEvidence(item, { onSaved }) }, 'Change')] : null));
}
