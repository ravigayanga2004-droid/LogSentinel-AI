# Authorized defensive use

Only submit logs from systems you own or are explicitly authorized to monitor. Do not collect credentials, bypass authentication, exploit systems, scan arbitrary targets, install stealth collectors, or use this platform for unauthorized surveillance.

The application parses supplied data, correlates observations and supports human investigation. It does not execute log content, probe configured hosts, exploit vulnerabilities, automatically block addresses, disable accounts or perform response actions. No offensive integrations are included.

Anomaly scores and rule matches are probabilistic signals. Verify maintenance activity, service changes, shared networks, parsing quality and normal operational context before making a judgment. Do not infer malicious intent or accuse individuals based solely on an alert. Keep notes factual and follow your organization's incident response and privacy processes.

Use separate workspaces where readers need different data access. Limit export rights. Protect database volumes, credentials and evidence downloads. Review retention and redaction before connecting production logs. Report implementation vulnerabilities privately to the repository maintainer; do not attach real sensitive logs or active credentials to public issues.
