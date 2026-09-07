# Operations

## Routine checks

1. Inspect the Azure dashboard and the `Referral processing failures` scheduled-query alert.
2. Query queue age, poison queue depth, worker failures, ACA restarts, SQL connectivity, authentication failures, and AI throttling.
3. Confirm no real-data incident signals. Stop intake immediately if a filename, support report, or scan indicates real personal, health, customer, or production content.
4. Review RBAC quarterly. Rotate the jumpbox admin password by resetting it on the VM (VM Access extension, `az vm user update`, or a redeploy with a new `JUMPBOX_ADMIN_PASSWORD`) and updating the `jumpbox-admin-password` Key Vault secret to match — the two are independent stores and are not kept in sync automatically. Or replace password access with Entra-based VM login.
5. Patch dependencies and base images, rebuild by commit SHA, validate, then use a single ACA active revision for rollback safety.

Useful KQL:

```kusto
AppTraces
| where TimeGenerated > ago(24h)
| where Message has_any ("referral", "queue", "extract")
| summarize count() by SeverityLevel, bin(TimeGenerated, 15m)
```

## Diagnostics

Every dependency sits behind a private endpoint, so troubleshoot from inside the API container rather than from a workstation. `az containerapp exec` runs there with the workload's managed identity:

```bash
APP=ca-referralintake-web-dev
RG=rg-referralintake

# Are both extraction endpoints reachable, and which analyzers does Content Understanding expose?
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose"

# Exercise the whole blob -> queue -> worker -> SQL path and clean up after itself.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --e2e"

# Inspect and clear referrals when SQL is otherwise unreachable.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --list"
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --delete <referral-id>"
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --delete failed"

# Create or refresh the Content Understanding custom analyzer.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --analyzer"

# Push the sample corpus through the real pipeline and grade both engines.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --score"
```

`--analyzer` is the only supported way to provision the analyzer by hand. The AI account has public network access disabled, so it cannot be created from CI or a workstation; the API also does this automatically at startup, and it is safe to rerun. It compares the live field schema against `api/referral/schema.py` and replaces the analyzer when they differ, because analyzers are immutable once created and editing the schema would otherwise silently have no effect.

`--score` uploads every document in `samples/` through the real blob -> queue -> worker path, compares the result against the ground truth in `samples/manifest.json`, and prints per-document and corpus accuracy for each engine before cleaning up after itself. The sample corpus ships inside the API image for this reason. Use it after changing `schema.py`, a field description, or an extractor to confirm the change actually helped:

```
=== fax-referral-transmission.png (Fax Systems, hard) ===
    documentIntelligence: 12/12 (100%)
    contentUnderstanding: 12/12 (100%)
=== Corpus totals ===
    documentIntelligence: 70/72 (97%)
    contentUnderstanding: 70/72 (97%)
```

Expect the handwritten scan to miss a field or two. That is the corpus doing its job: those are the referrals the human review step exists for.

`GET /api/health` reports `queueWorker: running|stopped`. If it reports `stopped`, referrals stay `queued` because nothing drains `referral-jobs`; check the API container logs for `referral.worker` entries.

Reviewers can also delete a referral from the UI. Deleting removes its row and blob and frees the document hash, which is what allows the same sample file to be uploaded again after a failure.

## Failure handling

- **Poison queue:** inspect metadata, not document contents, then replay only after the cause is fixed.
- **AI throttling/region outage:** leave status retriable and use exponential backoff; do not silently prefer one engine.
- **SQL unavailable:** the API must fail closed rather than accept an untracked upload.
- **Private DNS failure:** verify the Container Apps environment default-domain zone has its wildcard A record pointing to the environment static IP and is linked to both hub and spoke VNets; verify other private endpoint zones have the required spoke links.
- **Authentication failure:** verify app audience, issuer, redirect URI, and group assignment.

Backups are service native: configure SQL point-in-time/long-term retention to policy and validate blob soft-delete recovery. This sample enables seven-day Storage soft delete but does not claim a recovery objective. See [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview), [Storage data protection](https://learn.microsoft.com/azure/storage/blobs/data-protection-overview), [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/overview), and [Azure Bastion overview](https://learn.microsoft.com/azure/bastion/bastion-overview).
