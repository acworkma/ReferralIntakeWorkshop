# Guided walkthrough

This is the tour. It goes through the pipeline in the order a document does, and for each component it answers two questions: **why is this the right Azure service for this job**, and **where do I look in the portal to see it working**.

Every step has a portal path and a command-line equivalent. Prefer the portal when you are demonstrating; prefer the commands when you are debugging, because most of this workload is behind private endpoints and the portal cannot reach it from your laptop.

Resource names below use the defaults from `infra/main.bicepparam` (`referralintake`, `dev`) and the unique suffix your deployment generated. Replace `<suffix>` and `<sub>` with yours.

> **Before you start:** connect to `vm-referralintake-jump-dev` through Azure Bastion. The storage account, SQL, the AI services, the registry, and the function are all private. From your own machine you can see control-plane metadata and metrics, but not data.

---

## 0. Deliver a document

Open the app from the jumpbox browser and use **Deliver document**, or skip the app entirely:

```powershell
azcopy copy samples\referral-portal-submission.pdf `
  "https://streferralin<suffix>.blob.core.windows.net/incoming/referral-portal-submission.pdf"
```

Both do the same thing. That equivalence is the whole point of the design, and it is worth demonstrating both ways: the workflow does not know or care which one you used.

---

## 1. Blob Storage - the landing zone

**Why this service.** The architecture starts with a document arriving, so the first thing the platform needs is a durable place for it to arrive *at*. Blob storage gives that, plus something more useful: a document's container is its state. `incoming` means unclaimed, `processing` means the function owns it, `archive` and `failed` are terminal. That state lives in storage rather than only in a database, so it survives a database outage and is legible without a query.

**Why not a database or a file share.** A database row is a claim about a document; the blob *is* the document. Keeping the authoritative location in storage means there is one thing to reconcile, not two.

**Portal path.** Storage account `streferralin<suffix>` -> **Data storage** -> **Containers**. You will see `incoming`, `processing`, `archive`, and `failed`.

You will only see the contents from inside the VNet: **Networking** -> **Firewalls and virtual networks** shows public access disabled and the spoke subnet allowed. That is deliberate, and it is the reason the diagnostics run inside the container.

**Command line.**

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose --containers"
```

---

## 2. Event Grid - the trigger

**Why this service.** This is the component that makes the architecture what it claims to be. Without it, something has to *ask* whether a new document exists: a polling timer, or an API call from the app. Both make the caller the trigger, which is exactly the coupling the design is trying to avoid. Event Grid inverts it. Storage announces the arrival, and the pipeline reacts.

**Why it delivers to a queue instead of calling the function.** Event Grid push delivery cannot reach a private endpoint. The function has no public inbound path, by design. Delivering to a storage queue turns the last hop into an outbound pull by the function, so nothing needs to be exposed. It also buys retries and a poison queue at no cost.

**Why identity-based delivery.** The storage account has shared key access disabled, so there is no connection string for Event Grid to use. The system topic has its own managed identity holding exactly one role - Storage Queue Data Message Sender - scoped to the storage account. It can enqueue and do nothing else.

**Portal path.** Event Grid system topic `evgt-referralintake-dev` -> **Event Subscriptions** shows `referral-incoming`. Open it to see the `Microsoft.Storage.BlobCreated` filter and the subject prefix that restricts it to the `incoming` container - that filter is what stops the pipeline's own writes to `processing/` from re-triggering it.

Then **Metrics** on the system topic. Add `Published Events`, `Matched Events`, and `Delivery Succeeded Events`. Reading the three together tells you exactly where a missing document went:

| Symptom | Meaning |
|---|---|
| No published events | The blob never landed, or landed somewhere else |
| Published but not matched | The subject filter rejected it - wrong container |
| Matched but not delivered | The topic's identity cannot write to the queue |
| All three climbing | Event Grid did its job; look at the function |

**Command line.**

```bash
az monitor metrics list \
  --resource $(az eventgrid system-topic show -g rg-referralintake -n evgt-referralintake-dev --query id -o tsv) \
  --metric PublishSuccessCount MatchedEventCount DeliverySuccessCount DeliveryAttemptFailCount \
  --interval PT1M --start-time <utc-timestamp>
```

---

## 3. Storage queue - the buffer

**Why this service.** One buffer between the announcement and the work. It absorbs a burst, it survives the function restarting, and after five failed attempts it moves the message to `referral-jobs-poison` instead of retrying forever.

**A detail worth knowing.** Event Grid base64-encodes the event when it writes to a storage queue. The handler accepts both base64 and plain JSON, so the same code path works whether the message came from Event Grid or was written by hand for a test.

**Portal path.** Storage account -> **Data storage** -> **Queues** -> `referral-jobs`. From inside the VNet you can peek at messages here.

**Command line.**

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose --queue"
```

Depth should normally be zero: a message that sits here is a function that is not consuming.

---

## 4. Azure Functions - the orchestration

**Why this service.** The function does the work that touches the document: claim it, validate it, extract from it, compare, record. That is code, and it belongs in code. Functions gives it a queue trigger, VNet integration, and scale that follows queue depth without anyone managing a host.

**Why Elastic Premium and not Consumption.** Consumption cannot join a VNet, and every dependency here is behind a private endpoint.

**Why it ships as a container.** The function app's public network access is disabled. That also disables the SCM/Kudu endpoint that zip deployment publishes through. Setting a container image is an ARM operation, so it works over the control plane and needs no inbound path at all.

**The one thing to point out in the code.** The function moves the blob out of `incoming/` *before* it writes anything to the database. The move is the claim. Event Grid guarantees at-least-once delivery, so a duplicate event will arrive eventually; when it does, the blob is already gone and the second run stops. Idempotency is a property of the ordering, not of a lock.

**Portal path.** Function App `func-referralintake-dev` -> **Overview** shows the container image it is running. **Functions** -> `ReferralIntake` -> **Monitor** shows invocations.

Because public access is disabled, some portal blades will report that they cannot reach the app. Use ARM instead:

```bash
az rest --method GET --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-referralintake/providers/Microsoft.Web/sites/func-referralintake-dev/hostruntime/admin/host/status?api-version=2018-11-01"
```

A healthy response reports `"state": "Running"`. That call goes through the control plane, so it works from anywhere.

**Logs.** Log Analytics workspace `log-referralintake-dev` -> **Logs**:

```kusto
FunctionAppLogs
| where TimeGenerated > ago(1h)
| project TimeGenerated, Level, Category, Message
| order by TimeGenerated desc
```

You should see `Executing Functions.ReferralIntake`, the handler's own messages, and `Executed ... (Succeeded)`.

---

## 5. Document Intelligence and Content Understanding - the extraction

**Why two services.** One engine gives you an answer. Two give you an answer plus a signal about how much to trust it. Where they agree, a reviewer can skim; where they disagree, that is precisely where human attention is worth spending. The UI surfaces disagreements rather than burying them in a confidence score.

**Be clear with your audience:** the second engine is an addition to the reference architecture, not a copy of it. It is here because it makes the human-in-the-loop step demonstrably valuable instead of ceremonial.

**What the highlighted rows mean.** A row is flagged when the two engines *read the document differently*, which is not the same thing as low confidence and is the more useful signal. An engine can report 100% confidence and still be wrong; a disagreement between two independent reads is what surfaces that. In the review UI you will see rows where both engines are highly confident and still disagree - those are exactly the rows worth a human's attention.

Two things deliberately do *not* get flagged, because flagging them trains reviewers to ignore the highlight:

- **Formatting differences.** An NPI read as `1000 000079` by one engine and `1000000079` by the other is the same value. Whitespace is ignored when comparing. Punctuation is not, so `J44.1` against `144.1` stays flagged - that one is a real OCR error.
- **The generated summary.** Two engines will always word prose differently, so the summary is shown side by side and labelled as prose rather than reported as a disagreement.

To see the same decision from the command line, including which rows are flagged and why:

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose --compare latest"
```

**Why Document Intelligence for one side.** It is layout-grounded: it reads a scanned fax or a handwritten form as a document with structure, and returns coordinates and per-field confidence.

**Why Content Understanding for the other.** It works from a schema you define - the fields in `api/referral/schema.py` - and reasons about the content. On a clean digital PDF it is comparable; on a messy one it fails differently, which is what makes the comparison informative.

**Portal path.** Both accounts (`doc-referralintake-dev-<suffix>` and `ai-referralintake-dev-<suffix>`) -> **Networking** shows public access disabled and a private endpoint. -> **Metrics** shows call volume and latency.

**Command line.** To confirm both endpoints are reachable and see the analyzer schema currently deployed:

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose"
```

---

## 6. Azure SQL - the review queue

**Why this service.** Status, extraction comparisons, decisions, and reviewer identity are relational and need to be queried and audited. This is the one place a document's *history* lives, as opposed to its current location.

**Portal path.** SQL database `sqldb-referralintake` -> **Query editor** will not connect from your laptop; the server has no public endpoint. Connect from the jumpbox with SSMS or `sqlcmd` using Entra authentication.

Note that the workload authenticates with a managed identity, not a password. There is no connection string with a secret in it anywhere in this deployment.

**Command line.**

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose --list"
```

---

## 7. The Logic App - the business handoff

**Why this service.** The rule for splitting work between the function and the Logic App: **functions touch the document, Logic Apps touch the business.** Which system of record an approved referral goes to, who gets notified, what happens on a failure - those change for business reasons, by people who should not need a code deployment to change them. Putting them in the designer is what makes that possible.

**Portal path.** Logic App `logic-referralintake-notification-dev` -> **Logic app designer** shows the request trigger, the switch on event type, and the branches. -> **Runs history** shows one run per decision. Open a run and click into the trigger to see the exact payload the API sent.

Approve a referral in the app, then refresh the run history. A new run appears within seconds. That is Box 7 working.

**Command line.**

```bash
az rest --method GET --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-referralintake/providers/Microsoft.Logic/workflows/logic-referralintake-notification-dev/runs?api-version=2016-06-01"
```

---

## 8. The web app - what it is and is not

**Why it exists.** The workshop has no real upstream referral source and no real downstream system of record. The app stands in for both ends: it drops a document the way an upstream system would, and it shows a reviewer what the workflow produced.

**What it is not.** It is not the pipeline, and it never calls it. Delivering a document returns `202` with no referral id, because at that moment no referral exists - only a blob. The id appears when the function creates it, and the app finds out by polling like any other observer.

If you take one thing from this walkthrough, take that: **you could delete the web app and the pipeline would keep working.**

**What the screen shows.** Two views, and the split is real: **In flight** is anything the workflow still owns (claimed, extracting, awaiting review), **Decided** is anything that is finished (approved, returned, failed). Every referral is in exactly one of them.

Selecting a referral shows its position in the pipeline as a four step trail - Landed, Extracting, Awaiting review, Closed - and under the current step, **the container the document is physically in right now**. That is not a label the UI invented. The API reads it back off the blob URI, because in this design the container *is* the state. If you watch a document move from `incoming` to `processing` to `archive`, you are watching the same thing the storage account would tell you.

The one state worth waiting for is the first: right after you deliver, the document sits in `incoming` and the list shows it as **Landed, not yet claimed**. Nothing in the browser is making the next thing happen. That gap is the event reaching the function.

**Portal path.** Container App `ca-referralintake-web-dev` -> **Revisions** shows the active revision and both containers (`web` and `api`). -> **Ingress** shows it is internal to the VNet. -> **Authentication** shows Easy Auth in front of everything.

---

## 9. The network - why you could not click most of this

**Why hub and spoke.** The hub holds the things that let a human in: Azure Bastion and the jumpbox. The spoke holds the workload. Separating them means the administrative path can be governed independently of the application.

**Why private endpoints on everything.** Storage, SQL, the registry, both AI accounts, and the function each have a private endpoint and a private DNS zone. There is no public route to any of them. This is why the diagnostics run inside the container and why you connected through Bastion to see the app.

**Why the jumpbox has no public IP.** Bastion brokers the RDP session over TLS through the portal. Nothing about the VM is exposed.

**Portal path.** VNet `vnet-referralintake-spoke-dev` -> **Connected devices** lists every private endpoint NIC. Then **Private DNS zones** in the resource group: each `privatelink.*` zone is linked to the spoke, and the Container Apps environment domain zone is linked to both hub and spoke so the jumpbox can resolve the app.

---

## 10. Prove the whole thing

The acceptance test writes a document straight into the landing zone and makes no API call at all, then waits for it to appear in the review queue:

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose --drop"
```

A pass means Event Grid, the queue, the function, both AI services, and SQL are all working, and that none of them needed the application to ask.

To grade extraction quality across all six sample channels:

```bash
az containerapp exec -g rg-referralintake -n ca-referralintake-web-dev --container api \
  --command "python -m referral.diagnose --score"
```

Expect roughly 97% on both engines, with the misses concentrated in the handwritten scan and the fax. Those misses are the corpus doing its job: they are the referrals the human review step exists for.
