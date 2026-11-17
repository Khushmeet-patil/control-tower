# Control Tower: Security review (Phase 9)

Reviewed on 16 Nov 2026 against the code at the end of Phase 9. Each fix is pinned by a test in `backend/tests/test_security.py` (or the file named), so it cannot quietly regress. Re-run this review before go-live and after any change to sign-in, roles or file handling.

## What was checked

| Area | How | Result |
|---|---|---|
| Access control and scope | Read every service's `base_query` and permission checks; existing tests "a manager cannot see another branch" | Sound. One escalation path found (F8). |
| Sign-in and sessions | `auth` module, Flask-Login settings, cookies | Four issues (F1–F4) |
| Cross-site scripting | Searched the frontend for `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, inline handlers, `javascript:` URLs | None. All text goes through `el()` / `textContent`. Links from users are filtered (`safeLink`). |
| Cross-site request forgery | Writes are JSON-only (`app/__init__.py`), cookies `SameSite=Lax` | Sound: browsers cannot send cross-site JSON without CORS. |
| SQL injection | All queries use SQLAlchemy expressions; the one f-string query (backup row counts) uses a fixed table list | Sound |
| Open redirects | Login `next` parameter | Sound: only same-site paths (`/…`, not `//…`). |
| File uploads (imports) | Size, type, parsing, zip bombs | Sound after F5: 5 MB file limit, `.xlsx`/`.csv` only, openpyxl read-only mode, at most 5,000 rows, JSON body (no form posts). |
| Exports | Excel, CSV, PowerPoint, PDF | One issue (F9): formula injection. |
| Error handling | `app/core/errors.py` | Sound: unexpected errors return a generic message; details go to the log. |
| Passwords | `werkzeug` scrypt by default; minimum 8 characters | Sound |
| Dependencies | `pip-audit -r requirements.txt` | No known vulnerabilities. |

## Findings and fixes

| # | Finding | Risk | Fix | Test |
|---|---|---|---|---|
| F1 | Production started with the development `SECRET_KEY` if none was set | Anyone could forge a session cookie | The app refuses to start outside development and tests unless `SECRET_KEY` is set and at least 32 characters | `test_production_refuses_a_weak_secret_key` |
| F2 | Unlimited password attempts | Password guessing | After 5 wrong passwords in a row the account is locked for 15 minutes (`LOGIN_MAX_FAILURES`, `LOGIN_LOCK_MINUTES`); failures and locks are in the audit log | `test_account_locks_after_repeated_wrong_passwords` |
| F3 | Unknown emails were answered faster (no password hash checked) | Finding out which emails have accounts | A dummy hash is checked, and the message is the same | `test_unknown_emails_get_the_same_answer` |
| F4 | Changing or resetting a password left other sessions signed in; "remember me" lasted a year | A stolen session or laptop stays signed in after a reset | The session id carries a fingerprint of the password hash, so a new password ends every other session; changing your own keeps the current one. Remember-me now lasts 14 days. | `test_password_reset_signs_out_other_sessions`, `test_changing_your_own_password_keeps_you_signed_in_here` |
| F5 | No limit on request size; no Content Security Policy or HSTS | Memory exhaustion; weaker defence if a script injection were ever found | `MAX_CONTENT_LENGTH` 12 MB. Headers: CSP (`script-src 'self'`, no plugins, no framing by other sites), `Permissions-Policy`, `Cross-Origin-Opener-Policy`, HSTS in production, `Cache-Control: no-store` on the API | `test_security_headers`, `test_oversized_requests_are_refused` |
| F6 | Evidence links were only checked in the browser | A `javascript:` link could reach exports or future integrations | The server accepts only `http(s)://` evidence links | `test_evidence_links_must_be_web_addresses` |
| F7 | (Reliability, found while testing imports) SQLite's driver committed released savepoints for real | Import previews could save data | SQLAlchemy now starts SQLite transactions itself; MySQL was not affected | `tests/test_imports.py::test_preview_saves_nothing_and_reports_every_bad_cell` |
| F8 | A non-administrator holding `roles.manage` could give themselves the Administrator role, or create a role with any permission | Privilege escalation | Only administrators can grant permissions they do not hold or a scope wider than their own, in roles and when assigning roles to people | `test_role_managers_cannot_grant_more_than_they_hold` |
| F9 | Excel exports wrote text starting with `=` as a formula | A work item titled `=HYPERLINK(…)` runs in everyone's exported spreadsheet | Such text is written as text in every Excel file; CSV prefixes it with `'` | `tests/test_imports.py::test_excel_exports_never_turn_text_into_formulas`, `test_csv_export_neutralises_formulas` |

## Accepted risks

- **Lockout can be triggered by someone else.** Five wrong passwords lock a known account for 15 minutes. The lock is short, and the lock message reveals that the account exists. Both are the usual trade-off. With Microsoft Entra ID sign-in (Phase 10) and `ENTRA_ALLOW_PASSWORD=false`, only administrators still use passwords.
- **External tools do their own sign-in.** The Tool Centre controls who finds and opens a tool, but anyone who already has a tool's address can visit it directly (see Phase 7).
- **`style-src 'unsafe-inline'`** is allowed because the sign-in page uses a few style attributes. Scripts are strictly same-origin.
- **Role managers are trusted for scope.** `roles.manage` is held only by administrators by default.

## Before go-live

1. Set `FLASK_ENV=production`, a random `SECRET_KEY` (`python -c 'import secrets; print(secrets.token_urlsafe(48))'`) and serve over HTTPS only (secure cookies and HSTS assume it).
2. Run behind a reverse proxy with request rate limits on `/api/v1/auth/login`.
3. Schedule `flask --app run backup` daily, with `BACKUP_DIR` on another disk, and copy it off the server.
4. Change the seeded administrator's password, or remove the account after creating named administrators.

---

## Phase 10 additions (integrations, notifications)

Reviewed on 16 Nov 2026 with the Phase 10 code; each point is pinned by a test in `backend/tests/test_phase10.py`.

| Area | Design | Test |
|---|---|---|
| API tokens | 240 bits of randomness, prefixed `ct_`; only a SHA-256 hash is stored and the token is shown once. A token acts as its owner with the owner's **current** roles and scope (never more). `read` tokens cannot change anything; tokens cannot sign in, change passwords or make more tokens. Tokens expire (1–366 days; only calendar-only tokens may be open-ended) and can be revoked by their owner or an administrator. Changes made with a token are audited with source `api`. | `test_read_token_reads_with_the_owners_scope_only`, `test_write_token_changes_records_audited_as_api`, `test_revoked_and_expired_tokens_stop_working` |
| CSRF with tokens | Token requests carry an `Authorization` header, which browsers never add cross-site; cookie requests keep the JSON-only rule. | (existing CSRF tests) |
| Microsoft Entra ID | Authorisation code flow with PKCE (S256), `state` and `nonce`, a 10-minute window. The ID token's RS256 signature is checked against Microsoft's published keys, plus issuer, audience, expiry and nonce. Accounts are never created automatically: only an existing, active account is signed in, linked by email at first and by Entra object id afterwards (an account linked to a different Microsoft id is refused). The `next` address after sign-in must be a path on this site. | `test_entra_sign_in_links_the_account_by_email`, `test_entra_rejects_bad_state_nonce_or_unknown_people`, `test_next_address_must_stay_on_this_site` |
| Password sign-in off | With `ENTRA_ALLOW_PASSWORD=false` only administrators may use passwords (a way in if Microsoft is unavailable). | `test_entra_only_mode_blocks_passwords_except_for_admins` |
| Webhooks | Administrators only (`integrations.manage`). Only business records are sent (work, assignments, approvals, requests, time off, snapshots, scenarios, checklist answers), never people, roles, tokens or settings. Bodies are signed with HMAC-SHA256 using a per-webhook secret, shown once and rotatable. Messages are queued in the same transaction as the change (outbox), so rolled-back changes are never sent. Addresses are masked in the deliveries list (Teams addresses contain a secret). | `test_only_administrators_manage_webhooks`, `test_saved_changes_reach_webhooks_signed`, `test_failing_webhook_is_retried_then_marked_failed` |
| Notifications | Each person reads and marks only their own; links in notifications are site paths, and the browser follows only paths starting with `/`. | `test_people_see_only_their_own_notifications` |
| Tool context parameters | Only known placeholders are accepted; values are URL-encoded into the query string, never into the host or path. | `test_link_tools_get_project_data_in_the_address` |

**Accepted risks (Phase 10)**

- **Webhook addresses are trusted.** Administrators may point a webhook at any `http(s)` address, including internal ones. Webhooks are an administrator feature; give `integrations.manage` only to administrators.
- **Webhook secrets are stored in the database** (they are needed to sign each message). Database backups must be protected accordingly.
- **Calendar addresses carry their token in the URL** because calendar apps cannot send headers. They use a calendar-only token that opens nothing but that person's deadlines and time off, and can be revoked under My account.
