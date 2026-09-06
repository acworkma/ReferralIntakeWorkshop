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
| Function identity | Storage account | Storage Blob Data Contributor | Read/write source blobs |
| Function identity | Storage account | Storage Queue Data Contributor | Trigger and poison-queue processing |
| ACA identity | Storage account | Same two roles | API upload and enqueue |
| Function + ACA identities | Both AI accounts | Cognitive Services User | Token-authenticated inference |
| Function identity | Key Vault | Key Vault Secrets User | Future secret references; no list of management plane |
| Jumpbox admin group (`JUMPBOX_ADMIN_GROUP_OBJECT_ID`) | Key Vault | Key Vault Secrets User | Retrieve the jumpbox admin password (`jumpbox-admin-password` secret) for Bastion RDP sessions |
| ACA identity | ACR | AcrPull | Pull signed/approved workload images |
| Logic App identity | Storage account | Storage Blob Data Reader | Future read-only notification contract |

Azure SQL data-plane permissions are not Azure RBAC. From a private administrative host, run `scripts/bootstrap-sql.sql` as the configured Entra administrator. Remove `db_ddladmin` after first schema initialization; retain `db_datareader`/`db_datawriter`.

## Upload controls and remaining production work

This sample rejects unmarked filenames, unapproved types, oversized content, and MIME/signature mismatches. Before any sensitive-data use, add malware scanning, content disarm/reconstruction where required, data-loss-prevention policy, legal retention, immutable audit export, customer-managed keys if mandated, and a formal privacy/security assessment. [Microsoft Defender for Storage malware scanning](https://learn.microsoft.com/azure/defender-for-cloud/on-upload-malware-scanning) is recommended.

Defender plans are subscription-level and may affect unrelated resources and billing. Review them before deployment. Learn about [Defender for Cloud plans](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-cloud-introduction) and [managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview).
