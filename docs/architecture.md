# Architecture

## Purpose and boundary

This reference accepts PDF/JPEG/PNG referral documents that arrive in a storage account, extracts the same fields with two independent Azure AI services, compares them, and requires a human decision before anything is filed.

The important property is that **the workflow starts at the document, not at a request**. Nothing calls an API to begin processing. A blob appears in the landing zone and the pipeline runs, whether that blob came from this repository's simulator, from `azcopy`, from Storage Explorer, or from a real upstream referral source.

```text
                     ┌─ Box 1: documents arrive ────────────────────────┐
                     │  fax, email, portal, provider packet, partner    │
                     └───────────────────┬─────────────────────────────-┘
                                         │  (the web app stands in for these)
                                         v
                        Blob Storage: incoming/          <- Box 3, the landing zone
                                         │
                                    BlobCreated
                                         v
                              Event Grid system topic     <- the trigger
                                         │  identity-based delivery
                                         v
                              Storage queue referral-jobs
                                         │
                                         v
                     ┌─ Box 5: orchestration function ─────────────────┐
                     │  claim (move to processing/), validate,         │
                     │  extract twice, compare, write status           │
                     └───────┬──────────────────────┬──────────────────┘
                             │                      │
                Document Intelligence      Content Understanding
                             │                      │
                             └───────┬──────────────┘
                                     v
                              Azure SQL: needs_review    <- Box 6, the review queue
                                     │
                          reviewer approves or returns
                                     │
                     ┌───────────────┴───────────────┐
                     v                               v
              archive/ or failed/              Logic App        <- Box 7, the business handoff

Reviewer ──Entra──> private ACA ingress ──> web (nginx + React) + API
Hub VNet: Azure Bastion + Windows 11 jumpbox
Spoke VNet: ACA, the function, private endpoints, private DNS
Telemetry: Log Analytics <- Container Apps logs + FunctionAppLogs + Event Grid metrics
```

## Data flow

1. **A document lands in `incoming/`.** In the workshop the web app writes it there, because there is no real upstream system to connect to. The app is a simulator for Box 1, not the pipeline. `azcopy copy sample.pdf "https://<account>.blob.core.windows.net/incoming/sample.pdf"` from the jumpbox produces exactly the same result.

2. **Event Grid raises `Microsoft.Storage.BlobCreated`** and delivers it to the `referral-jobs` storage queue. Delivery is identity-based, because the storage account has shared key access disabled. The subscription filters on the `incoming` container so the pipeline's own writes to `processing/`, `archive/`, and `failed/` do not re-trigger it.

   Event Grid delivers to a queue rather than calling the function directly because Event Grid push delivery cannot reach a private endpoint. Queueing keeps every hop outbound, so the function needs no inbound public path at all.

3. **The queue-triggered function claims the document** by moving the blob from `incoming/` to `processing/<referral-id>/`. The move is the claim, and it happens before any database write. That ordering is what makes Event Grid's at-least-once delivery safe: a redelivered event finds the blob gone and stops.

4. **Guardrails run against the claimed document**: allow-listed MIME type, matching magic number, 10 MiB limit, and a content hash that rejects a document already in the system. A rejected document moves to `failed/` with a recorded reason rather than disappearing.

5. **Both extraction engines run** against the same bytes: Document Intelligence for layout-grounded field extraction, Content Understanding for a schema-driven read of the same fields. The function writes a field-level comparison and sets the referral to `needs_review`.

   Two engines is an addition to the reference architecture, not a copy of it. It exists so the workshop can show where the engines disagree, which is exactly where a human's attention is worth the most.

6. **A reviewer sees the queue** in the web app, with confidence scores and every disagreement called out, and approves or returns the referral with an audit note.

7. **The decision moves the document to `archive/` or `failed/` and posts a business event to the Logic App.** Where an approved referral is routed and who hears about a failure are business decisions, so they live in the Logic App designer rather than in application code.

## Why each piece is here

| Component | Implementation | Why this and not something else |
|---|---|---|
| Landing zone | Blob containers `incoming`, `processing`, `archive`, `failed` | A referral's container is its state. Storage is the source of truth about where a document is, so the state survives a database outage and is visible without a query. |
| Trigger | Event Grid system topic on the storage account | The architecture says a document arriving starts the work. A polling timer or an API call would make the app the trigger, which is the thing this design is avoiding. |
| Buffer | Storage queue `referral-jobs` + `referral-jobs-poison` | Event Grid push cannot reach a private endpoint. The queue turns the delivery into an outbound pull, and gives retries and a poison queue for free. |
| Orchestration | Queue-triggered Azure Function, containerised, Elastic Premium | Functions touch the document. VNet integration and scale-to-demand come with the plan; the container image exists because the app has no public SCM endpoint to zip-deploy through. |
| Business rules | Consumption Logic App | Logic Apps touch the business. Routing and notification change without a code deployment, which is the point of separating them. |
| Extraction | Document Intelligence + Azure AI Content Understanding | Two independent reads make disagreement visible. One engine gives an answer; two give an answer and a confidence signal a human can act on. |
| Review state | Azure SQL | Status, comparisons, decisions, and reviewer identity are relational and audited. |
| Simulator + review UI | React 19 + nginx and a FastAPI sidecar in one Container App | Stands in for the systems on either end of the workflow. It writes to `incoming/` and reads from SQL, and it never invokes the pipeline. |
| Network | Hub/spoke VNets, NSGs, private endpoints, private DNS | Every data service is reachable only from inside the VNet. There is no public path to storage, SQL, the registry, the AI services, or the function. |
| Admin access | Windows 11 jumpbox behind Azure Bastion | The workshop needs a place inside the VNet to run diagnostics and browse the app. The VM has no public IP. |
| Security | Managed identities, RBAC, Key Vault, Defender | No connection strings and no keys. Every hop authenticates as an identity with a scoped role. |
| Operations | Log Analytics, Application Insights, a failure alert | Container Apps logs, `FunctionAppLogs`, and Event Grid delivery metrics all land in one workspace. |

See [Azure Container Apps networking](https://learn.microsoft.com/azure/container-apps/networking), [Event Grid delivery and retry](https://learn.microsoft.com/azure/event-grid/delivery-and-retry), [private endpoints](https://learn.microsoft.com/azure/private-link/private-endpoint-overview), and [Azure Functions networking](https://learn.microsoft.com/azure/azure-functions/functions-networking-options).
