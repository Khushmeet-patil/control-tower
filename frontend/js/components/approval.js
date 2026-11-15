/**
 * Approval building blocks, shared by the Approvals inbox, the item page and My Home.
 *
 *   approvalBadge('pending')                 → "Awaiting approval" badge (null when there is nothing to say)
 *   createStepTracker(request)               → the chain's steps with who decided what
 *   openReview(requestId, { onDone })        → review dialog: evidence, earlier decisions, checklist, approve/reject
 *   openComplete(item, { onDone })           → "Mark complete" dialog (evidence link, finish date, remarks)
 */
import { api } from '../core/api.js';
import { el, formatDate, formatDateTime } from '../core/utils.js';
import { createBadge } from './badge.js';
import { createForm, openFormModal } from './form-builder.js';
import { openModal } from './modal.js';
import { createPersonCell } from './person.js';
import { showError, showToast } from './toast.js';
import { safeLink } from './work-table.js';

const STATUS = {
  pending: ['Awaiting approval', 'var(--ct-warning)'],
  approved: ['Approved', 'var(--ct-success)'],
  rejected: ['Returned', 'var(--ct-danger)'],
  cancelled: ['Withdrawn', 'var(--ct-text-subtle)'],
};
const STEP = {
  approved: ['Approved', 'var(--ct-success)'],
  rejected: ['Rejected', 'var(--ct-danger)'],
  skipped: ['Skipped', 'var(--ct-text-subtle)'],
  waiting: ['Waiting', 'var(--ct-warning)'],
  blocked: ['Nobody to ask', 'var(--ct-danger)'],
  upcoming: ['Next', 'var(--ct-border-strong)'],
  not_reached: ['Not reached', 'var(--ct-border-strong)'],
};

export function approvalBadge(status, { showApproved = true } = {}) {
  if (!status || (status === 'approved' && !showApproved)) return null;
  const [label, color] = STATUS[status] || [status, null];
  return createBadge(label, color);
}

/** Who must act now, in words. */
export function waitingOn(request) {
  if (request.status !== 'pending') return STATUS[request.status]?.[0] || request.status;
  if (request.current_approver) return request.current_approver.full_name;
  if (request.current_role) return `Anyone with the ${request.current_role} role`;
  return 'Nobody yet (an administrator can decide)';
}

export function createStepTracker(request) {
  return el('ol', { class: 'ct-steps' }, request.steps.map((s) => {
    const [label, color] = STEP[s.state] || [s.state, null];
    const d = s.decision;
    const current = request.status === 'pending' && s.index === request.current_step;
    return el('li', { class: `ct-steps__item is-${s.state}` },
      el('span', { class: 'ct-steps__dot', style: { background: color } }),
      el('div', { class: 'ct-steps__body' },
        el('div', { class: 'ct-steps__title' }, `${s.index + 1}. ${s.name}`, ' ', createBadge(label, color)),
        el('div', { class: 'ct-muted ct-small' }, s.approver_kind_label,
          current ? ` · waiting on ${waitingOn(request)}` : ''),
        current && request.waiting_note ? el('div', { class: 'ct-small' }, request.waiting_note) : null,
        d ? el('div', { class: 'ct-small' },
          d.approver ? `${d.approver.full_name}, ` : '', formatDateTime(d.decided_at),
          d.comment ? el('div', { class: 'ct-steps__comment' }, `“${d.comment}”`) : null) : null));
  }));
}

export async function openReview(requestId, { onDone } = {}) {
  let r;
  try { r = await api.get(`/approvals/${requestId}`); } catch (err) { showError(err); return; }
  const step = r.current_step !== null ? r.steps[r.current_step] : null;
  const checks = step?.checklist || [];
  const boxes = checks.map((c) => el('input', { type: 'checkbox', value: c }));
  const comment = createForm({
    fields: [{ key: 'comment', label: step?.require_comment ? 'Comment (required to approve; always required to reject)' : 'Comment (required to reject: say what must be fixed)', type: 'textarea', full: true }],
    columns: 1,
  });
  const error = el('div', { class: 'ct-form-error ct-hidden', role: 'alert' });
  const item = r.work_item;

  const body = el('div', { class: 'ct-stack' },
    el('div', {},
      el('a', { href: `/pages/item.html?id=${item.id}&tab=approvals` }, `${item.code} ${item.title}`),
      el('div', { class: 'ct-muted ct-small' }, `${r.chain_name} · marked complete by ${r.submitted_by?.full_name || 'the system'} on ${formatDate(r.submitted_at)}`,
        r.waiting_days ? ` · waiting ${r.waiting_days} day(s)` : '')),
    el('div', {}, el('strong', {}, 'Evidence: '), item.evidence_url ? safeLink(item.evidence_url, item.evidence_url) : el('span', { class: 'ct-text-danger' }, 'none provided')),
    createStepTracker(r),
    r.can_decide && step ? el('div', { class: 'ct-stack' },
      checks.length ? el('fieldset', { class: 'ct-checklist' },
        el('legend', {}, `Before approving “${step.name}”, confirm:`),
        checks.map((c, i) => el('label', { class: 'ct-checkbox' }, boxes[i], c))) : null,
      error, comment.element) : null);

  const decide = async (approve, close) => {
    error.classList.add('ct-hidden');
    const ticked = boxes.filter((b) => b.checked).map((b) => b.value);
    const { comment: text } = comment.getValues();
    if (approve && ticked.length < checks.length) return showFormError('Tick every check before approving.');
    if (!approve && !text) return showFormError('Say what must be fixed before rejecting.');
    try {
      await api.post(`/approvals/${r.id}/${approve ? 'approve' : 'reject'}`, { comment: text, checklist: ticked, version: r.version });
      close();
      showToast(approve ? 'Approved' : 'Sent back with your note', 'success');
      onDone?.();
    } catch (err) { comment.setErrors(err); }
  };
  function showFormError(message) {
    error.textContent = message;
    error.classList.remove('ct-hidden');
  }

  const actions = [{ label: 'Close' }];
  if (r.can_retry) actions.unshift({ label: 'Look for an approver again', onClick: async (close) => { await api.post(`/approvals/${r.id}/retry`, {}); close(); onDone?.(); } });
  if (r.can_withdraw && !r.can_decide) actions.unshift({ label: 'Withdraw', variant: 'danger', onClick: (close) => { close(); openWithdraw(r, { onDone }); } });
  if (r.can_decide) {
    actions.push({ label: 'Reject: send back', variant: 'danger', onClick: (close) => decide(false, close) });
    actions.push({ label: 'Approve: I take responsibility', variant: 'primary', onClick: (close) => decide(true, close) });
  }
  openModal({ title: r.can_decide ? `Review · ${step.name}` : `Approval · ${item.code}`, body, actions, wide: true });
}

export function openWithdraw(request, { onDone } = {}) {
  openFormModal({
    title: `Withdraw approval of ${request.work_item.code}?`, wide: false,
    intro: 'The item goes back to In progress. Mark it complete again when it is ready.',
    fields: [{ key: 'reason', label: 'Reason', required: true, full: true }],
    submitLabel: 'Withdraw',
    onSubmit: (v) => api.post(`/approvals/${request.id}/withdraw`, v),
    onDone: () => { showToast('Approval withdrawn', 'success'); onDone?.(); },
  });
}

export function openComplete(item, { onDone } = {}) {
  openFormModal({
    title: `Mark ${item.code} complete`,
    intro: 'If this kind of work needs approval, it goes to the approvers now and counts towards progress once they approve.',
    fields: [
      { key: 'evidence_url', label: 'Evidence / deliverable link', type: 'url', placeholder: 'https://', full: true, help: 'Approvers review this. Milestones need one.' },
      { key: 'actual_end', label: 'Finished on', type: 'date', help: 'Empty = today.' },
      { key: 'remarks', label: 'Remarks', type: 'textarea' },
    ],
    values: { evidence_url: item.evidence_url, actual_end: item.actual_end },
    submitLabel: 'Mark complete',
    onSubmit: (v) => api.post(`/work-items/${item.id}/complete`, v),
    onDone: (saved) => {
      showToast(saved.approval_status === 'pending' ? 'Marked complete: sent for approval' : 'Marked complete', 'success');
      onDone?.(saved);
    },
  });
}
