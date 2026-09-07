# Operations

## Routine checks

1. Check the `Referral processing failures` scheduled-query alert.
2. Check Event Grid delivery, the poison queue, function executions, ACA restarts, SQL connectivity, authentication failures, and AI throttling.
3. Review RBAC quarterly. Rotate the jumpbox admin password by resetting it on the VM (VM Access extension, `az vm user update`, or a redeploy with a new `JUMPBOX_ADMIN_PASSWORD`) and updating the `jumpbox-admin-password` Key Vault secret to match — the two are independent stores and are not kept in sync automatically. Or replace password access with Entra-based VM login.
4. Patch dependencies and base images, rebuild by commit SHA, validate, then use a single ACA active revision for rollback safety.

Useful KQL. The workload writes to two tables, not to `AppTraces`: the Container App logs to `ContainerAppConsoleLogs_CL` and the orchestration function to `FunctionAppLogs`.

```kusto
// What has the orchestration function been doing?
FunctionAppLogs
| where TimeGenerated > ago(24h)
| project TimeGenerated, Level, Category, Message
| order by TimeGenerated desc
```

```kusto
// Anything failing on either side.
union isfuzzy=true
    (FunctionAppLogs | where Level == "Error" | project TimeGenerated, Message),
    (ContainerAppConsoleLogs_CL | where Log_s has "failed" | project TimeGenerated, Message = Log_s)
| where TimeGenerated > ago(24h)
| order by TimeGenerated desc
```

## Following a document through the pipeline

When a document does not appear in the review queue, work forward along the path. Each step has a place to look, and the first one that reports nothing is where the problem is.

**1. Did the blob land?** `--containers` lists every container in the landing zone. A document still sitting in `incoming/` means the trigger never fired or the function never claimed it.

**2. Did Event Grid publish and deliver?** The system topic's metrics answer this without any log query:

```bash
az monitor metrics list \
  --resource $(az eventgrid system-topic show -g rg-referralintake -n evgt-referralintake-dev --query id -o tsv) \
  --metric PublishSuccessCount MatchedEventCount DeliverySuccessCount DeliveryAttemptFailCount \
  --start-time 2026-01-01T00:00:00Z
```

`PublishSuccessCount` without `MatchedEventCount` means the subscription filter rejected the event — check that the blob really went to the `incoming` container. `MatchedEventCount` without `DeliverySuccessCount` means the topic's identity cannot write to the queue.

**3. Is the message stuck in the queue?** `--queue` reports the depth of `referral-jobs` and `referral-jobs-poison`. A message sitting in the jobs queue means the function is not consuming; a message in the poison queue means it consumed and failed five times.

**4. Did the function run?** `FunctionAppLogs` carries every invocation. No rows at all means the host is not running the trigger:

```bash
az rest --method GET --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-referralintake/providers/Microsoft.Web/sites/func-referralintake-dev/hostruntime/admin/host/status?api-version=2018-11-01"
```

That call goes through ARM, so it works even though the function app has no public network access.

## Diagnostics

Every dependency sits behind a private endpoint, so troubleshoot from inside the API container rather than from a workstation. `az containerapp exec` runs there with the workload's managed identity:

```bash
APP=ca-referralintake-web-dev
RG=rg-referralintake

# Are both extraction endpoints reachable, and which analyzers does Content Understanding expose?
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose"

# The acceptance test: write a sample straight into incoming/ with no API call,
# then wait for the workflow to put it in the review queue.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --drop"

# What is in each container of the landing zone?
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --containers"

# Queue and poison queue depth, with a peek at the first message.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --queue"

# Inspect and clear referrals when SQL is otherwise unreachable.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --list"
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --delete <referral-id>"
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --delete failed"

# Show a referral's extracted rows and which ones the review UI flags, and why.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --compare latest"

# Drive a decision through Box 7 without a browser session.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --review <referral-id> approve"

# Create or refresh the Content Understanding custom analyzer.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --analyzer"

# Push the sample corpus through the real pipeline and grade both engines.
az containerapp exec -g $RG -n $APP --container api --command "python -m referral.diagnose --score"
```

`--drop` is the one to run after any deployment. It proves the property the whole design rests on: a document that nothing asked about still gets processed. It makes no API call, so a pass means Event Grid, the queue, the function, both AI services, and SQL are all working.

`--analyzer` is the only supported way to provision the analyzer by hand. The AI account has public network access disabled, so it cannot be created from CI or a workstation; the API also does this automatically at startup, and it is safe to rerun. It compares the live field schema against `api/referral/schema.py` and replaces the analyzer when they differ, because analyzers are immutable once created and editing the schema would otherwise silently have no effect.

`--score` drops every document in `samples/` into `incoming/` and lets the real trigger process it, compares the result against the ground truth in `samples/manifest.json`, and prints per-document and corpus accuracy for each engine before cleaning up after itself. The sample corpus ships inside the API image for this reason. Use it after changing `schema.py`, a field description, or an extractor to confirm the change actually helped:

```
=== fax-referral-transmission.png (Fax Systems, hard) ===
    documentIntelligence: 12/12 (100%)
    contentUnderstanding: 12/12 (100%)
=== Corpus totals ===
    documentIntelligence: 70/72 (97%)
    contentUnderstanding: 70/72 (97%)
```

Expect the handwritten scan to miss a field or two. That is the corpus doing its job: those are the referrals the human review step exists for.

Reviewers can also delete a referral from the UI. Deleting removes its row and blob and frees the document hash, which is what allows the same sample file to be delivered again after a failure.

## Failure handling

- **Poison queue:** a message lands there after five failed attempts. Inspect metadata, not document contents, then replay only after the cause is fixed.
- **A document stuck in `processing/`:** the function claimed it and then failed hard. The referral row carries a `failureReason`; the document stays where it is so nothing is lost.
- **AI throttling/region outage:** leave status retriable and use exponential backoff; do not silently prefer one engine.
- **SQL unavailable:** the function fails after claiming the document, which leaves it in `processing/` rather than accepting untracked work.
- **Private DNS failure:** verify the Container Apps environment default-domain zone has its wildcard A record pointing to the environment static IP and is linked to both hub and spoke VNets; verify other private endpoint zones have the required spoke links.
- **Authentication failure:** verify app audience, issuer, redirect URI, and group assignment.

Backups are service native: configure SQL point-in-time/long-term retention to policy and validate blob soft-delete recovery. This sample enables seven-day Storage soft delete but does not claim a recovery objective. See [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview), [Storage data protection](https://learn.microsoft.com/azure/storage/blobs/data-protection-overview), [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/overview), and [Azure Bastion overview](https://learn.microsoft.com/azure/bastion/bastion-overview).
