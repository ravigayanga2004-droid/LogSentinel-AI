# Alert investigation workflow

Alerts move among NEW, ACKNOWLEDGED, INVESTIGATING, RESOLVED, FALSE_POSITIVE, SUPPRESSED and REOPENED. Administrators and analysts can update them; viewers and source administrators read evidence but cannot triage. Normal UI operations never permanently delete alerts.

1. Open the alert inbox or assigned investigations. Filter by severity, status, assignee, source, title or time range.
2. Read **Why this was flagged**. Compare observed value, threshold, window, confidence and version with local expectations. An anomaly is not proof of misconduct.
3. Review chronological evidence and related events. Source/IP/user correlation uses installation-keyed hashes within a 15-minute neighborhood. Do not assume one IP always identifies one person.
4. Assign a workspace member, acknowledge the alert, and move it to INVESTIGATING. Record verified facts, maintenance context and follow-up tasks in notes. Attach evidence references as needed.
5. Adjust severity if the evidence supports it. Add short tags for team organization. Recommended next steps are suggestions; the platform does not perform system actions.
6. Resolve with a reason, or mark FALSE_POSITIVE with the reason tuning is needed. SUPPRESSED requires an expiration, capped at 30 days. Suppression affects new matching alerts; the existing record remains visible. Use REOPENED to resume review.

Every update and note creates an audit entry. Assignment/status updates generate an in-app notification for the relevant member/workspace. An alert page includes similar rule observations and the resource's activity history. Notes are redacted before persistence, but operators must still avoid inserting private material unnecessarily.

Rule cooldown deduplicates repeated matching groups for the configured period. Ingestion retries do not create duplicate evidence or alerts. Expired suppressions resume detection. The alert's triggering explanation remains a snapshot; newly arriving evidence can produce a later observation after cooldown. Source-silence and statistical alerts can be aggregate observations with no individual evidence rows.

Event and alert retention are separate. An open alert survives alert cleanup, but old related events may expire under event retention. The alert still retains its explanation, count and audit history. Reports may include a bounded copy of evidence; manage their storage/download lifecycle under the same privacy policy.
