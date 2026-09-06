# Operations

## Routine checks

1. Inspect the Azure dashboard and the `Referral processing failures` scheduled-query alert.
2. Query queue age, poison queue depth, Function failures, ACA restarts, SQL connectivity, authentication failures, and AI throttling.
3. Confirm no real-data incident signals. Stop intake immediately if a filename, support report, or scan indicates real personal, health, customer, or production content.
4. Review RBAC quarterly. Rotate the jumpbox admin password through a controlled secret process, or replace password access with Entra-based VM login.
5. Patch dependencies and base images, rebuild by commit SHA, validate, then use a single ACA active revision for rollback safety.

Useful KQL:

```kusto
AppTraces
| where TimeGenerated > ago(24h)
| where Message has_any ("referral", "queue", "extract")
| summarize count() by SeverityLevel, bin(TimeGenerated, 15m)
```

## Failure handling

- **Poison queue:** inspect metadata, not document contents, then replay only after the cause is fixed.
- **AI throttling/region outage:** leave status retriable and use exponential backoff; do not silently prefer one engine.
- **SQL unavailable:** the API must fail closed rather than accept an untracked upload.
- **Private DNS failure:** verify the Container Apps environment default-domain zone has its wildcard A record pointing to the environment static IP and is linked to both hub and spoke VNets; verify other private endpoint zones have the required spoke links.
- **Authentication failure:** verify app audience, issuer, redirect URI, and group assignment.

Backups are service native: configure SQL point-in-time/long-term retention to policy and validate blob soft-delete recovery. This sample enables seven-day Storage soft delete but does not claim a recovery objective. See [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview), [Storage data protection](https://learn.microsoft.com/azure/storage/blobs/data-protection-overview), [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/overview), and [Azure Bastion overview](https://learn.microsoft.com/azure/bastion/bastion-overview).
