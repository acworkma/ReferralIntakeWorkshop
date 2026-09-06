# Architecture

## Purpose and boundary

This reference accepts PDF/JPEG/PNG documents, queues extraction, compares two Azure AI extraction paths, and requires a human decision. It does not integrate with a customer system and contains no customer identifiers, schemas, names, or sample records.

```text
Reviewer ──Entra──> private ACA ingress
                       ├─ web (nginx + React)
                       └─ API sidecar ──> Azure SQL (status/audit)
                                      ├─> Blob Storage (source documents)
                                      ├─> Queue Storage
                                      └─ queue worker thread
                                               ├─> Document Intelligence
                                               ├─> Content Understanding
                                               └─> Azure SQL (comparison/progress)

Hub VNet: Azure Bastion (Basic) + Windows 11 jumpbox
Spoke VNet: ACA, Functions integration, private endpoints, private DNS
Telemetry: App Insights → Log Analytics → alert/dashboard
```

## Data flow

1. Container Apps authentication redirects an unauthenticated reviewer to Microsoft Entra ID. The API rejects requests without the injected principal header. `LOCAL_MOCK_IDENTITY=true` is a test-only fixture that the API refuses to honor whenever it detects it is running in Azure (`WEBSITE_INSTANCE_ID` set).
2. The upload endpoint requires an allow-listed MIME type, a matching magic number, and a 10 MiB limit.
3. The API hashes the file, writes it to the private `referrals` blob container, inserts a queued status in SQL, and sends only the referral ID to Queue Storage.
4. A queue-worker thread inside the API container reads the blob using managed identity, records processing progress, calls both extraction services, and writes a field-level comparison. Running the worker in the API container means a deployment that only rolls the container images is fully functional; the message stays on the queue until it succeeds, and after `QUEUE_MAX_DEQUEUE` attempts the referral is marked `failed` and the message moves to `referral-jobs-poison`.
5. The web UI polls SQL-backed API state. A reviewer sees confidence and disagreements, then approves or rejects with an audit note, and can delete a referral to remove it and free its document for re-upload.
6. The disabled Logic App is an intentional extension point for approved outbound notifications. Enable it only after its connector, destination, and data contract pass security review.

## Components

| Component | Implementation | Responsibility |
|---|---|---|
| Web | React 19, Vite, TypeScript, nginx | Responsive queue/review UI and same-origin API proxy |
| API | FastAPI sidecar | Validation, identity interpretation, status, and review endpoints |
| Worker | Queue-consumer thread in the API container | Asynchronous dual extraction with retry and poison handling |
| Queue/blob | StorageV2 ZRS | Durable jobs and source documents |
| Status | Azure SQL | Workflow state, comparisons, decisions, and reviewer identity |
| AI | Document Intelligence + Azure AI Services | Independent extraction paths |
| Compute | Private ACA + Functions Premium | Internal application and worker |
| Network | Standalone hub/spoke, NSGs, private DNS/endpoints | Isolation and name resolution |
| Admin | Windows 11 jumpbox behind Azure Bastion (Basic) | Private administration via RDP, no public IP on the VM |
| Security | Key Vault, managed identities, RBAC, Defender | Secretless workload access and posture |
| Operations | Log Analytics, App Insights, dashboard, alert | Central telemetry and failure detection |
| Integration | Disabled Consumption Logic App | Reviewed future notification flow |

See [Azure Container Apps networking](https://learn.microsoft.com/azure/container-apps/networking), [private endpoints](https://learn.microsoft.com/azure/private-link/private-endpoint-overview), and [Azure Functions networking](https://learn.microsoft.com/azure/azure-functions/functions-networking-options).
