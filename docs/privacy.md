# Privacy and data handling

Logs often contain personal data and credentials. Collect the minimum required information from authorized systems. Determine an appropriate legal/organizational basis and communicate monitoring policies to affected users. This software does not make that decision for the operator.

Before staging, recursive redaction removes password, token, secret, cookie, authorization, API-key, session identifier, email and personal-identifier fields; message redaction handles common key/value forms and Bearer credentials. IP message masking defaults on. Structured source IPs, destination IPs and usernames use installation-keyed HMACs, including when message IP masking is disabled. URL queries/fragments are discarded. Admin-configured literal masks handle installation-specific values without allowing regex execution.

Redaction is a defense-in-depth heuristic, not a proof that arbitrary free text is anonymous. Unlabelled secrets and unusual formats may not be recognized. Use parser previews and custom masks before importing sensitive samples. Restrict account names, source labels and notes too. No raw-message persistence toggle is offered: raw storage is unavailable.

Staging files contain redacted normalized envelopes or safe row errors, not raw input. The worker deletes a completed import's staging file. Failed jobs keep redacted staging for retry; administrators should inspect abandoned staging as described in operations. Backups, exports and filesystem snapshots create additional copies and require corresponding retention and access policies.

Retention defaults to 30 days for events, 180 days for closed alerts, and 365 days for audit records. These defaults are visible; automatic deletion starts disabled. Administrators can preview and confirm a manual cleanup or explicitly enable daily cleanup. Event retention also expires report copies and notifications. Open alerts stay, though their old evidence may expire. Every cleanup records counts in a new audit entry. Data cleanup is irreversible; maintain a reviewed backup policy.

Policy changes apply to future ingestion and export. Already-stored messages are not retroactively reprocessed by changing a mask. To remove previously stored personal data, the operator must use a reviewed migration/retention procedure and account for backups/exports. Audit history remains subject to configured retention.

No logs go to an external AI provider. Optional SMTP transmits only password-reset email and its expiring link to the configured relay. Browser local storage holds theme/workspace preferences; cookies hold session and CSRF values. Display timezone is user-configurable; storage is UTC. Pseudonymous hashes still count as potentially sensitive correlation data.
