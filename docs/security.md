# Security model

## Trust boundaries

- The internet has no route to the application: the Container Apps environment is internal and the Function, SQL, Storage, Key Vault, ACR (when switched), and AI accounts use private endpoints.
- Access begins from a connected corporate network, VPN/ExpressRoute, or an Azure Bastion session to the jumpbox VM. Microsoft Entra authentication is mandatory at ACA and Function front doors.
- The API never treats a client-supplied user name as identity. Azure injects the principal; the test-only mock identity fixture uses the conspicuous `.invalid` user and is refused whenever the API detects it is running in Azure.
- Files and queue messages stay on managed-service private links. Queue messages contain IDs, not document contents.
- Workloads use managed identities; local keys are disabled for Storage, AI, and App Insights.

## Built-in RBAC assignments

| Principal | Scope | Role | Why |
|---|---|---|---|
| Function identity | Storage account | Storage Blob Data Contributor | Claim a document out of `incoming/` and move it as it progresses |
| Function identity | Storage account | Storage Queue Data Contributor | Consume the trigger queue and write to the poison queue |
| ACA identity | Storage account | Same two roles | Deliver a document into `incoming/`, read it back for review, and inspect queue depth from the diagnostics CLI |
| Function + ACA identities | Both AI accounts | Cognitive Services User | Token-authenticated inference |
| Event Grid system topic identity | Storage account | Storage Queue Data Message Sender | Deliver blob events to `referral-jobs`, and nothing else. The storage account has shared key access disabled, so delivery must be identity-based. |
| Jumpbox admin group (`JUMPBOX_ADMIN_GROUP_OBJECT_ID`) | Key Vault | Key Vault Secrets User | Retrieve the jumpbox admin password (`jumpbox-admin-password` secret) for Bastion RDP sessions |
| ACA + function identities | ACR | AcrPull | Pull signed/approved workload images |

Azure SQL data-plane permissions are not Azure RBAC. From a private administrative host, run `scripts/bootstrap-sql.sql` as the configured Entra administrator. Remove `db_ddladmin` after first schema initialization; retain `db_datareader`/`db_datawriter`.

## Intake controls and remaining production work

This sample rejects unapproved types, oversized content, MIME/signature mismatches, and documents whose content hash is already in the system. Those checks run in the orchestration function, after the document has been claimed, so a rejected document is recorded and moved to `failed/` with a reason rather than silently dropped.

Before any sensitive-data use, add malware scanning, content disarm/reconstruction where required, data-loss-prevention policy, legal retention, immutable audit export, customer-managed keys if mandated, and a formal privacy/security assessment. [Microsoft Defender for Storage malware scanning](https://learn.microsoft.com/azure/defender-for-cloud/on-upload-malware-scanning) is recommended.

One interaction to plan for: Defender's on-upload malware scanning delivers through an Event Grid system topic, and Azure allows only one system topic per storage account - a slot this workload's trigger already occupies. Scanning documents before they reach the pipeline therefore needs a deliberate design rather than just enabling the plan. See [deployment](deployment.md#event-grid-and-defender-for-storage-share-one-slot).

Defender plans are subscription-level and may affect unrelated resources and billing. Review them before deployment. Learn about [Defender for Cloud plans](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-cloud-introduction) and [managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview).
