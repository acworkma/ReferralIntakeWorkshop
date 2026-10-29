# Manual Azure portal deployment

Step-by-step portal clicks to build the referral intake workshop one resource at a time. Each section tells you **where to go**, **what to enter on each tab**, **how to put the resource on the VNet**, and **what to do right after it is created**. Background, permissions, and troubleshooting are in the [appendix](#appendix).

- Automated alternative: [Bicep deployment guide](deployment.md). Architecture: [architecture.md](architecture.md).
- Use synthetic data only. All values below come from [`infra/main.bicepparam`](../infra/main.bicepparam) and the [`infra/modules`](../infra/modules) templates.
- **Images are required before the apps will work.** The three application images (`referral-web`, `referral-api`, `referral-func`) must be built from this repo and pushed to your registry by your build team. The portal cannot build them. See [step 12](#12-container-registry).

## Before you start: values

Pick one lowercase 3-8 character alphanumeric `<suffix>` and use it everywhere.

| Item | Value |
|---|---|
| Resource group | `rg-referralintake` |
| Main region | **East US 2** |
| SQL region | **Central US** |
| Content Understanding region | **West US 3** |
| Tags (every resource) | `workload=referralintake`, `environment=dev`, `managedBy=portal` |
| SQL admin | Existing Entra group (name + object ID) |
| Jumpbox login | `azureadmin` + password from your secret store |

How each resource connects to the network:

| Resource | How it is on the VNet |
|---|---|
| Key Vault, Storage (blob + queue), SQL, Document Intelligence, AI Services, Container Registry | Private endpoint in spoke `snet-private-endpoints` |
| Container Apps environment | Injected into spoke `snet-aca`, internal IP only |
| Function App | Outbound VNet integration into spoke `snet-functions` **and** private endpoint in `snet-private-endpoints` |
| Bastion / Jumpbox | Hub `AzureBastionSubnet` / `snet-jumpbox` |
| Log Analytics, Application Insights | Azure Monitor Private Link Scope (AMPLS) private endpoint in `snet-private-endpoints` ([step 4](#4-monitoring)); public access switched off in [step 18.2](#182-make-monitoring-private-only) |
| Logic App (Consumption) | Multi-tenant service; it **cannot** be placed in a VNet or given a private endpoint. Its trigger is locked to the spoke's NAT gateway IP ([step 13](#13-logic-app-consumption)). For a fully private Logic App use Standard (step 13, option B) |
| Event Grid system topic | Platform service; system topics **cannot** be put in a VNet or given a private endpoint. It delivers into the private storage queue with its managed identity and the storage trusted-service exception ([step 8](#8-event-grid-system-topic)) |
| Managed identities | Not network resources (they are Entra identities), so there is nothing to attach. They are used by the Container App and Function App, which are on the VNet |

Nothing in this design needs public network access except the Bastion public IP and, until the images are pushed, the container registry.

Create resources in the order below. Record the values marked **Record** as you go.

---

## 1. Admin one-time setup

Done once by a subscription admin.

**Register resource providers.** Portal: **Subscriptions** > your subscription > **Settings > Resource providers**. Search each and click **Register** if not already *Registered*:

`Microsoft.App`, `Microsoft.Web`, `Microsoft.Storage`, `Microsoft.EventGrid`, `Microsoft.Sql`, `Microsoft.CognitiveServices`, `Microsoft.KeyVault`, `Microsoft.ManagedIdentity`, `Microsoft.Network`, `Microsoft.OperationalInsights`, `Microsoft.Insights`, `Microsoft.Security`, `Microsoft.ContainerRegistry`, `Microsoft.Logic`, `Microsoft.Compute`

**Create the resource group.** Portal: **Resource groups > + Create**. Name `rg-referralintake`, region East US 2 > **Review + create > Create**.

**Give the deployer access.** **rg-referralintake > Access control (IAM) > + Add > Add role assignment**:
- **Contributor** > deployer user/group.
- If the deployer will also do the role assignments in this guide, add **Role Based Access Control Administrator** on the resource group as well; otherwise an admin does each "Role assignments" step.

**Create the app registration.** Portal: **Microsoft Entra ID > App registrations > + New registration**:

| Field | Value |
|---|---|
| Name | `app-referralintake-dev` |
| Supported account types | Accounts in this organizational directory only |
| Redirect URI | Leave blank (added in steps 15 and 16) |

Click **Register**. Then:
1. **Expose an API > Application ID URI > Add** > accept `api://<client-id>` > **Save**.
2. **Authentication > Implicit grant and hybrid flows** > check **ID tokens** > **Save**.
3. **Record** Application (client) ID and Directory (tenant) ID from **Overview**.

---

## 2. Virtual networks

### 2.1 Network security groups

Portal: **Network security groups > + Create**, region East US 2. Create three: `nsg-referralintake-hub-dev`, `nsg-referralintake-workload-dev`, `nsg-referralintake-bastion-dev`.

Then open each > **Settings > Inbound/Outbound security rules > + Add**. Source port is always `*`. Use **Service Tag** as source/destination type for named tags.

| NSG | Dir | Priority | Name | Source | Destination | Protocol / port | Action |
|---|---|---|---|---|---|---|---|
| hub | In | 200 | `AllowBastionRdpInbound` | `10.20.1.0/26` | Any | TCP / 3389 | Allow |
| hub | In | 4096 | `DenyInternetInbound` | Internet | Any | Any / * | Deny |
| workload | In | 100 | `AllowAzureLoadBalancer` | AzureLoadBalancer | Any | Any / * | Allow |
| workload | In | 4096 | `DenyInternetInbound` | Internet | Any | Any / * | Deny |
| bastion | In | 120 | `AllowHttpsInbound` | Internet | Any | TCP / 443 | Allow |
| bastion | In | 130 | `AllowGatewayManagerInbound` | GatewayManager | Any | TCP / 443 | Allow |
| bastion | In | 140 | `AllowAzureLoadBalancerInbound` | AzureLoadBalancer | Any | TCP / 443 | Allow |
| bastion | In | 150 | `AllowBastionHostCommunicationInbound` | VirtualNetwork | VirtualNetwork | Any / 8080,5701 | Allow |
| bastion | In | 4096 | `DenyAllInbound` | Any | Any | Any / * | Deny |
| bastion | Out | 100 | `AllowSshRdpOutbound` | Any | VirtualNetwork | Any / 22,3389 | Allow |
| bastion | Out | 110 | `AllowAzureCloudOutbound` | Any | AzureCloud | TCP / 443 | Allow |
| bastion | Out | 120 | `AllowBastionCommunicationOutbound` | VirtualNetwork | VirtualNetwork | Any / 8080,5701 | Allow |
| bastion | Out | 130 | `AllowHttpOutbound` | Any | Internet | Any / 80 | Allow |

### 2.2 Hub VNet

Portal: **Virtual networks > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region | `vnet-referralintake-hub-dev` / East US 2 |
| IP addresses | Address space | `10.20.0.0/16` (delete the `default` subnet) |
| IP addresses | + Add subnet | Purpose **Azure Bastion**: `AzureBastionSubnet`, `10.20.1.0/26`, NSG `nsg-referralintake-bastion-dev` |
| IP addresses | + Add subnet | `snet-jumpbox`, `10.20.2.0/24`, NSG `nsg-referralintake-hub-dev` |

**Review + create > Create.**

### 2.3 Spoke VNet

Portal: **Virtual networks > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region | `vnet-referralintake-spoke-dev` / East US 2 |
| IP addresses | Address space | `10.21.0.0/16` (delete the `default` subnet) |
| IP addresses | + Add subnet | `snet-aca`, `10.21.0.0/23`, NSG workload, **Subnet delegation** `Microsoft.App/environments` |
| IP addresses | + Add subnet | `snet-functions`, `10.21.2.0/24`, NSG workload, **Subnet delegation** `Microsoft.Web/serverFarms` |
| IP addresses | + Add subnet | `snet-private-endpoints`, `10.21.3.0/24`, NSG workload, **Private endpoint network policy** Disabled |

**Review + create > Create.**

### 2.4 Peering

Portal: **vnet-referralintake-hub-dev > Settings > Peerings > + Add**:

| Field | Value |
|---|---|
| Remote peering link name | `peer-to-hub` |
| Remote virtual network | `vnet-referralintake-spoke-dev` |
| Remote: allow access / allow forwarded traffic | Checked / Checked |
| Local peering link name | `peer-to-spoke` |
| Local: allow access / allow forwarded traffic | Checked / Checked |
| Gateway / route server options | Unchecked |

**Add.** Check both peerings show **Connected**.

> **Private DNS zones:** you do not create them here. Each private endpoint below creates its zone when you choose **Integrate with private DNS zone = Yes**, and links it to the spoke. Each section then links that zone to the hub so the jumpbox can resolve it.

**Link a zone to the hub** (used throughout): **Private DNS zones** > zone > **DNS Management > Virtual network links > + Add** > Link name `link-vnet-referralintake-hub-dev`, Virtual network `vnet-referralintake-hub-dev`, auto registration **off** > **Create**. Skip if the zone already has a hub link.

---

## 3. Bastion and jumpbox

You use the jumpbox browser for every step that touches private data (storage containers, SQL, Key Vault secrets, testing).

### 3.1 Bastion

Portal: **Bastions > + Create**.

| Field | Value |
|---|---|
| Name / Region | `bas-referralintake-dev` / East US 2 |
| Tier | **Basic** |
| Virtual network | `vnet-referralintake-hub-dev` (uses `AzureBastionSubnet`) |
| Public IP | **Create new** `pip-bastion-referralintake-dev` (Standard, Static) |

### 3.2 Jumpbox VM

Portal: **Virtual machines > + Create > Azure virtual machine**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region | `vm-referralintake-jump-dev` / East US 2 |
| Basics | Security type | Trusted launch |
| Basics | Image | Windows 11 Pro, version 25H2 |
| Basics | Size | `Standard_D2as_v5` |
| Basics | Username / password | `azureadmin` / your password |
| Basics | Public inbound ports | **None** |
| Disks | OS disk type | Premium SSD LRS |
| **Networking** | Virtual network / Subnet | `vnet-referralintake-hub-dev` / `snet-jumpbox` |
| **Networking** | Public IP | **None** |
| **Networking** | NIC network security group | **None** (subnet NSG applies) |
| Management | System assigned managed identity | On |

**Check:** **VM > Connect > Bastion** signs in. Open Edge inside the VM and sign in to `portal.azure.com`.

---

## 4. Monitoring

Log Analytics and Application Insights cannot be injected into a subnet. They go on the VNet through an **Azure Monitor Private Link Scope (AMPLS)** and one private endpoint. (The Bicep template leaves them public; this is the private equivalent.)

**Log Analytics:** **Log Analytics workspaces > + Create** > name `log-referralintake-dev`, East US 2 > **Create**. Then **Usage and estimated costs > Data retention** = 30 days.

**Application Insights:** **Application Insights > + Create** > name `appi-referralintake-dev`, East US 2, Workspace `log-referralintake-dev` > **Create**. **Record** the **Connection string** from **Overview**.

**Put monitoring on the VNet (AMPLS):**

1. Portal: **Monitor > Settings > Private Link Scopes > + Create**:

   | Field | Value |
   |---|---|
   | Resource group / Name | `rg-referralintake` / `ampls-referralintake-dev` |
   | Query access mode / Ingestion access mode | **Open** / **Open** (keep Open; it only affects other monitoring resources reached from this VNet) |

   **Review + create > Create.**
2. **ampls-referralintake-dev > Azure Monitor Resources > + Add** > select `log-referralintake-dev` and `appi-referralintake-dev` > **Apply**.
3. **Private Endpoint connections > + Private endpoint**:

   | Tab | Field | Value |
   |---|---|---|
   | Basics | Name / Region | `pe-ampls-referralintake-dev` / East US 2 |
   | Resource | Resource type / Resource / Target sub-resource | `Microsoft.insights/privateLinkScopes` / `ampls-referralintake-dev` / `azuremonitor` |
   | Virtual Network | Virtual network / Subnet | `vnet-referralintake-spoke-dev` / `snet-private-endpoints` |
   | DNS | Integrate with private DNS zone | **Yes** (creates five zones, below) |

   **Review + create > Create.**
4. Link all five zones to the hub ([how](#24-peering)): `privatelink.monitor.azure.com`, `privatelink.oms.opinsights.azure.com`, `privatelink.ods.opinsights.azure.com`, `privatelink.agentsvc.azure-automation.net`, `privatelink.blob.core.windows.net`. Storage (step 7) reuses the blob zone; select the existing zone there.

> AMPLS changes how *every* Azure Monitor endpoint resolves for networks linked to these zones. If your hub DNS is shared with other workloads, agree this with the network owner. Microsoft recommends one AMPLS per shared DNS.

Public access is switched off in [step 18.2](#182-make-monitoring-private-only), after the apps are sending data.

---

## 5. Managed identities

No network step: a managed identity is an Entra identity, not a network resource. It gets VNet traffic through the Container App and Function App it is attached to. Portal: **Managed Identities > + Create**, East US 2. Create:

- `id-referralintake-func-dev`
- `id-referralintake-aca-dev`

**Record** for each: **Client ID** and **Object (principal) ID** (Overview).

---

## 6. Key Vault

Portal: **Key vaults > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region / Tier | `kv-referralintake-<suffix>` / East US 2 / Standard |
| Basics | Days to retain deleted vaults / Purge protection | 90 / **Enable** |
| Access configuration | Permission model | **Azure role-based access control** |
| **Networking** | Enable public access | **Unchecked** |
| **Networking** | Private endpoint | **+ Create a private endpoint** (below) |

**Private endpoint (on the VNet):**

| Field | Value |
|---|---|
| Name / Location | `pe-kv-referralintake-<suffix>` / East US 2 |
| Target sub-resource | `vault` |
| Virtual network / Subnet | `vnet-referralintake-spoke-dev` / `snet-private-endpoints` |
| Integrate with private DNS zone | **Yes** > `privatelink.vaultcore.azure.net` |

**Review + create > Create.**

**After create:**
1. Link `privatelink.vaultcore.azure.net` to the hub ([how](#24-peering)).
2. **Access control (IAM) > + Add role assignment** > **Key Vault Secrets Officer** > yourself (to add the secret).
3. From the jumpbox browser: **Objects > Secrets > + Generate/Import** > name `jumpbox-admin-password`, value = the VM password.
4. Optional: **IAM** > **Key Vault Secrets User** > jumpbox admin group.

---

## 7. Storage account

Portal: **Storage accounts > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region | `streferralindev<suffix>` / East US 2 |
| Basics | Primary service / Performance / Redundancy | Blob Storage / Standard / **ZRS** |
| Advanced | Require secure transfer / Min TLS | On / 1.2 |
| Advanced | Allow anonymous access on containers | **Off** |
| Advanced | Enable storage account key access | **Off** |
| Advanced | Default to Microsoft Entra authorization in the portal | **On** |
| Advanced | Hierarchical namespace | Off |
| **Networking** | Network access | **Disable public access and use private access** |
| **Networking** | Private endpoint | **+ Add private endpoint** twice (below) |
| Data protection | Soft delete for blobs / containers | On, 7 days / On, 7 days |

**Private endpoints (on the VNet):**

| Field | Endpoint 1 | Endpoint 2 |
|---|---|---|
| Name / Location | `pe-streferralindev<suffix>-blob` / East US 2 | `pe-streferralindev<suffix>-queue` / East US 2 |
| Storage sub-resource | `blob` | `queue` |
| Virtual network / Subnet | spoke / `snet-private-endpoints` | spoke / `snet-private-endpoints` |
| Integrate with private DNS zone | Yes > `privatelink.blob.core.windows.net` (existing zone from step 4) | Yes > `privatelink.queue.core.windows.net` |

**Review + create > Create.**

**After create:**
1. Link both zones to the hub ([how](#24-peering)).
2. **Access control (IAM) > + Add role assignment** (select **Managed identity** under Members):

   | Role | Members |
   |---|---|
   | Storage Blob Data Contributor | `id-referralintake-func-dev`, `id-referralintake-aca-dev`, and yourself |
   | Storage Queue Data Contributor | `id-referralintake-func-dev`, `id-referralintake-aca-dev`, and yourself |

3. From the jumpbox browser: **Data storage > Containers > + Container** (private): `incoming`, `processing`, `failed`, `archive`.
4. **Data storage > Queues > + Queue**: `referral-jobs`, `referral-jobs-poison`.

---

## 8. Event Grid system topic

Event Grid **system** topics cannot be placed in a VNet or given a private endpoint (Event Grid private endpoints exist only for custom topics, domains, and namespaces, which this design does not use). Instead, the topic's managed identity delivers into the private storage queue through the storage trusted-service exception below; no public access is turned on. Create it right after storage (only one system topic is allowed per storage account; if Defender already created one, see the appendix).

Portal: **Event Grid System Topics > + Create**.

| Field | Value |
|---|---|
| Topic type | Storage Accounts (Blob & GPv2) |
| Resource | `streferralindev<suffix>` |
| Name | `evgt-referralintake-dev` |
| Enable system assigned identity | **On** |

**After create:**
1. **Storage account > Access control (IAM) > + Add role assignment** > **Storage Queue Data Message Sender** > Managed identity > System topic `evgt-referralintake-dev`.
2. **Storage account > Security + networking > Networking > Firewalls and virtual networks**:
   - **Resource instances** > Resource type `Microsoft.EventGrid/systemTopics`, Instance `evgt-referralintake-dev`.
   - **Exceptions** > check **Allow Azure services on the trusted services list to access this storage account**.
   - **Save.** Leave public network access disabled. If this page is hidden while public access is disabled, see the appendix.

The event subscription is created in [step 17](#17-event-subscription), after the apps are running.

---

## 9. SQL server and database

Portal: **SQL databases > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Database name | `sqldb-referralintake` |
| Basics | Server | **Create new**: `sql-referralintake-dev-centra-<suffix>`, location **Central US** |
| Basics | Authentication | **Use Microsoft Entra-only authentication**; Set admin = SQL admin group |
| Basics | Elastic pool / Workload | No / Development |
| Basics | Compute + storage | **Standard S0** |
| Basics | Backup storage redundancy | Locally-redundant |
| **Networking** | Connectivity method | **Private endpoint** |
| **Networking** | Private endpoints | **+ Add private endpoint** (below) |
| **Networking** | Minimum TLS version | 1.2 |

**Private endpoint (on the VNet):**

| Field | Value |
|---|---|
| Name / Location | `pe-sql-referralintake-dev-centra-<suffix>` / **East US 2** (VNet region) |
| Target sub-resource | `SqlServer` |
| Virtual network / Subnet | spoke / `snet-private-endpoints` |
| Integrate with private DNS zone | **Yes** > `privatelink.database.windows.net` |

**Review + create > Create.**

**After create:**
1. Link `privatelink.database.windows.net` to the hub ([how](#24-peering)).
2. **SQL server > Security > Networking > Public access** = **Disable**.
3. From the jumpbox browser, as a member of the SQL admin group: **sqldb-referralintake > Query editor** > **Continue as \<you\>** > run:

```sql
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'id-referralintake-func-dev')
    CREATE USER [id-referralintake-func-dev] FROM EXTERNAL PROVIDER;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'id-referralintake-aca-dev')
    CREATE USER [id-referralintake-aca-dev] FROM EXTERNAL PROVIDER;

ALTER ROLE db_datareader ADD MEMBER [id-referralintake-func-dev];
ALTER ROLE db_datawriter ADD MEMBER [id-referralintake-func-dev];
ALTER ROLE db_ddladmin ADD MEMBER [id-referralintake-func-dev];
ALTER ROLE db_datareader ADD MEMBER [id-referralintake-aca-dev];
ALTER ROLE db_datawriter ADD MEMBER [id-referralintake-aca-dev];
ALTER ROLE db_ddladmin ADD MEMBER [id-referralintake-aca-dev];
```

The app creates its tables on first start. **Record** the server name `<server>.database.windows.net`.

---

## 10. Document Intelligence

Portal: **Document Intelligence > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region / Pricing tier | `doc-referralintake-dev-<suffix>` / East US 2 / **S0** |
| **Network** | Type | **Disabled** (no networks, private endpoint only) |
| **Network** | Private endpoint | **+ Add private endpoint** (below) |

**Private endpoint (on the VNet):**

| Field | Value |
|---|---|
| Name / Location | `pe-doc-referralintake-dev-<suffix>` / East US 2 |
| Sub-resource | `account` |
| Virtual network / Subnet | spoke / `snet-private-endpoints` |
| Integrate with private DNS zone | **Yes** > `privatelink.cognitiveservices.azure.com` |

**Review + create > Create.**

**After create:**
1. Link `privatelink.cognitiveservices.azure.com` to the hub ([how](#24-peering)).
2. **Access control (IAM)** > **Cognitive Services User** > both managed identities.
3. **Record** the endpoint (**Keys and Endpoint** page; `https://doc-referralintake-dev-<suffix>.cognitiveservices.azure.com/`).

---

## 11. AI Services (Content Understanding) and models

Portal: **Azure AI services / Microsoft Foundry > + Create** an **Azure AI Services** (multi-service) resource.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region / Pricing tier | `ai-referralintake-dev-<suffix>` / **West US 3** / **S0** |
| **Network** | Type | **Disabled** |
| **Network** | Private endpoint | **+ Add private endpoint** (below) |

**Private endpoint (on the VNet):**

| Field | Value |
|---|---|
| Name / Location | `pe-ai-referralintake-dev-<suffix>` / **East US 2** (VNet region) |
| Sub-resource | `account` |
| Virtual network / Subnet | spoke / `snet-private-endpoints` |
| Integrate with private DNS zone | **Yes** > existing `privatelink.cognitiveservices.azure.com` |

**Review + create > Create.**

**After create:**
1. **Access control (IAM)** > **Cognitive Services User** > both managed identities.
2. **Record** the endpoint (**Keys and Endpoint**).
3. **Deploy models**: from the jumpbox browser, **Overview > Go to Foundry portal > Models + endpoints > + Deploy model > Deploy base model**. Deploy one at a time into **this** resource:

   | Model | Version | Deployment name | Deployment type | Capacity |
   |---|---|---|---|---|
   | `gpt-5.2` | `2025-12-11` | `gpt-5.2` | Global Standard | 50K TPM |
   | `text-embedding-3-large` | `1` | `text-embedding-3-large` | Global Standard | 50K TPM |

The API creates the `referralIntake` analyzer itself on startup.

---

## 12. Container registry

Portal: **Container registries > + Create**.

| Tab | Field | Value |
|---|---|---|
| Basics | Registry name / Location / SKU | `crreferralintakedev<suffix>` / East US 2 / **Premium** |
| Basics | Role assignment permissions mode | **RBAC Registry Permissions** |
| **Networking** | Connectivity | **Public access** (lets your build team push; locked down after create) |

**Review + create > Create.**

**Private endpoint (on the VNet):** **Registry > Settings > Networking > Private access > + Create a private endpoint connection**:

| Field | Value |
|---|---|
| Name / Location | `pe-crreferralintakedev<suffix>` / East US 2 |
| Sub-resource | `registry` |
| Virtual network / Subnet | spoke / `snet-private-endpoints` |
| Integrate with private DNS zone | **Yes** > `privatelink.azurecr.io` |

**Create.**

**After create:**
1. Link `privatelink.azurecr.io` to the hub ([how](#24-peering)).
2. **Settings > Networking > Public access**: check **Allow trusted Microsoft services**. Once images are pushed (or if your build agent is inside the VNet), set **Public network access = Disabled**.
3. **Properties**: Admin user **Disabled**. **Settings > Networking**: **Dedicated data endpoint** enabled. **Policies > Retention**: enabled, 7 days.
4. **Access control (IAM)** > **AcrPull** > both managed identities.
5. **Record** the **Login server** (Overview).
6. **Push images (outside the portal).** Build team pushes from repo source, `linux/amd64`, immutable tags:

   | Repository | Dockerfile / build context |
   |---|---|
   | `referral-web` | [`web/Dockerfile`](../web/Dockerfile) / `web` |
   | `referral-api` | [`api/Dockerfile`](../api/Dockerfile) / repo root |
   | `referral-func` | [`functions/Dockerfile`](../functions/Dockerfile) / repo root |

**Check:** **Services > Repositories** lists all three with tags. Do not continue to steps 14-15 without them.

---

## 13. Logic App (Consumption)

A Consumption Logic App is multi-tenant: it **cannot** be placed in a VNet or given a private endpoint. Option A (matches the template) keeps Consumption and restricts its trigger to traffic from your spoke. Option B makes it fully private but goes beyond the template.

### Option A: Consumption, trigger locked to the spoke

**First, give the spoke a fixed outbound IP.** The Container App and Function App call the Logic App from `snet-aca` and `snet-functions`. Portal: **NAT gateways > + Create**:

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region / Availability zone | `ng-referralintake-dev` / East US 2 / No zone |
| Outbound IP | Public IP addresses | **Create a new public IP address**: `pip-ng-referralintake-dev` |
| Subnet | Virtual network / Subnets | `vnet-referralintake-spoke-dev` / check `snet-aca` and `snet-functions` |

**Review + create > Create.** **Record** the public IP address. (A NAT gateway on `snet-aca` requires the **Workload profiles** environment used in step 14.)

**Create the Logic App.** Portal: **Logic apps > + Add > Consumption (Multi-tenant)** > name `logic-referralintake-notification-dev`, East US 2 > **Create**.

**After create:**
1. **Settings > Identity > System assigned** = On > **Save**.
2. **Development Tools > Logic app code view**, replace `definition` with:

```json
{
  "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
  "contentVersion": "1.0.0.0",
  "triggers": {
    "manual": {
      "type": "Request",
      "kind": "Http",
      "inputs": {
        "method": "POST",
        "schema": {
          "type": "object",
          "required": ["event"],
          "properties": {
            "event": { "type": "string" },
            "referralId": { "type": "string" },
            "filename": { "type": "string" },
            "patientName": { "type": "string" },
            "reviewedBy": { "type": "string" },
            "reason": { "type": "string" },
            "occurredAt": { "type": "string" }
          }
        }
      }
    }
  },
  "actions": {
    "Route_event": {
      "type": "Switch",
      "expression": "@triggerBody()?['event']",
      "cases": {
        "Intake_failed": {
          "case": "referral.failed",
          "actions": {
            "Raise_intake_failure": {
              "type": "Compose",
              "inputs": {
                "severity": "error",
                "summary": "Referral intake failed for @{triggerBody()?['filename']}",
                "reason": "@triggerBody()?['reason']",
                "detail": "The document is in the failed container and did not reach the review queue. Add a Teams, Outlook, or ticketing action here to page whoever owns intake.",
                "payload": "@triggerBody()"
              }
            }
          }
        }
      },
      "default": {
        "actions": {
          "Record_review_decision": {
            "type": "Compose",
            "inputs": {
              "severity": "information",
              "summary": "@{triggerBody()?['event']} for @{triggerBody()?['filename']}",
              "reviewedBy": "@triggerBody()?['reviewedBy']",
              "detail": "A reviewer reached a decision. Add a downstream action here to hand the referral to the system of record.",
              "payload": "@triggerBody()"
            }
          }
        }
      }
    },
    "Acknowledge": {
      "type": "Response",
      "kind": "Http",
      "runAfter": { "Route_event": ["Succeeded"] },
      "inputs": {
        "statusCode": 202,
        "body": { "accepted": true, "event": "@triggerBody()?['event']" }
      }
    }
  },
  "outputs": {}
}
```

3. **Save.** Open **Logic app designer** > the trigger > **Record** the **HTTP URL** (`LOGIC_APP_URL`). It is a secret.
4. **Settings > Workflow settings > Access control configuration**: **Trigger access option** = **Specific IP ranges**, **IP ranges for triggers** = `<NAT gateway IP>/32` > **Save**. Only the spoke can now call the trigger.

### Option B: Logic App Standard on the VNet (beyond the template)

Use this only if policy forbids any multi-tenant endpoint. Logic App Standard runs on an App Service plan, so it gets the same VNet integration and private endpoint as the Function App:

1. **Spoke VNet > Subnets > + Subnet**: `snet-logic`, `10.21.4.0/24`, delegation `Microsoft.Web/serverFarms`, NSG `nsg-referralintake-workload-dev`.
2. **Logic apps > + Add > Standard (Workflow Service Plan)**, plan **WS1**. **Networking**: Enable public access **Off**, Enable network injection **On**, inbound private endpoint in `snet-private-endpoints` with private DNS zone `privatelink.azurewebsites.net` (the Function App in step 15 reuses it), outbound VNet integration `snet-logic`. Link the zone to the hub ([how](#24-peering)).
3. Its storage account must also be private (blob, queue, table, and file private endpoints). Follow [Secure traffic between Standard logic apps and virtual networks](https://learn.microsoft.com/azure/logic-apps/secure-single-tenant-workflow-virtual-network-private-endpoint).
4. Create a **Stateful** workflow, paste the same `definition`, and use its trigger URL as `LOGIC_APP_URL`. Skip the NAT gateway and IP restriction in option A.

---

## 14. Container App (web + API)

### 14.1 Create the environment and app

Portal: **Container Apps > + Create > Container App**.

| Tab | Field | Value |
|---|---|---|
| Basics | Container app name / Region | `ca-referralintake-web-dev` / East US 2 |
| Basics | Container Apps environment | **Create new** (below) |
| Container | Use quickstart image | Unchecked |
| Container | Name / Image source | `web` / Azure Container Registry |
| Container | Registry / Image / Tag | `crreferralintakedev<suffix>` / `referral-web` / your tag |
| Container | Authentication / Identity | **Managed identity** / `id-referralintake-aca-dev` |
| Container | CPU and memory | 0.5 cores, 1 Gi |
| Container | Environment variables | `API_BASE_URL` = `http://127.0.0.1:7071` |
| Ingress | Ingress / Traffic | Enabled / **Accepting traffic from anywhere** (the internal environment keeps it private) |
| Ingress | Type / Transport / Insecure | HTTP / Auto / unchecked |
| Ingress | Target port | `8080` |

**Create new environment:**

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Zone redundancy | `cae-referralintake-dev` / Disabled |
| Basics | Environment type | **Workload profiles** |
| Monitoring | Logs destination | Azure Log Analytics > `log-referralintake-dev` |
| **Networking** | Use your own virtual network | **Yes** |
| **Networking** | Virtual network / Infrastructure subnet | `vnet-referralintake-spoke-dev` / `snet-aca` |
| **Networking** | Virtual IP | **Internal** |

**Create** the environment, then **Review + create > Create** the app.

### 14.2 Private DNS for the environment

1. **cae-referralintake-dev > Overview**: **Record** **Default domain** and **Static IP**.
2. **Private DNS zones > + Create** > Name = the **default domain** exactly > **Create**.
3. Zone > **+ Record set** > Name `*`, Type A, TTL 300 seconds, IP = static IP.
4. Zone > **Virtual network links**: add **spoke** (`link-vnet-referralintake-spoke-dev`) and **hub** (`link-vnet-referralintake-hub-dev`), auto registration off.

### 14.3 Add the API container and settings

**ca-referralintake-web-dev > Application > Revisions and replicas > Create new revision**:

1. **Container image > + Add > App container**: name `api`, ACR `referral-api` + tag, managed identity `id-referralintake-aca-dev`, 0.5 CPU / 1 Gi.
2. On `api` > **Environment variables**, add the [app settings](#16-app-settings) using the ACA identity client ID. For `LOGIC_APP_URL`, first add it under **Settings > Secrets** and choose **Reference a secret**.
3. On `web` > **Health probes > Liveness**: HTTP GET `/`, port 8080, initial delay 10, period 30.
4. **Scale**: min **1**, max **3**, **+ Add** rule `http`, HTTP scaling, concurrent requests **50**.
5. **Create.**

### 14.4 Sign-in

1. **Record** the **Application Url** (Overview).
2. **App registration > Authentication > + Add a platform > Web** > Redirect URI `https://<web-fqdn>/.auth/login/aad/callback` > **Configure**.
3. **Container App > Security > Authentication > Add identity provider > Microsoft**:

   | Field | Value |
   |---|---|
   | App registration type | **Provide the details of an existing app registration** |
   | Application (client) ID | app registration client ID |
   | Client secret | Leave empty |
   | Issuer URL | `https://sts.windows.net/<tenant-id>/v2.0` |
   | Allowed token audiences | `api://<client-id>` |
   | Restrict access | Require authentication |
   | Unauthenticated requests | HTTP 302 redirect |
   | Token store | Off |

**Check:** from the jumpbox browser, the app URL redirects to sign-in and then loads.

---

## 15. Function App

Portal: **Function App > + Create > Functions Premium**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Region | `func-referralintake-dev` / East US 2 |
| Basics | Deploy as container image | **Yes**, Operating system Linux |
| Basics | Plan | **Create new** `asp-referralintake-func-dev`, **Elastic Premium EP1** |
| Storage | Storage account | `streferralindev<suffix>` |
| Container | Image source / Registry / Image / Tag | Azure Container Registry / `crreferralintakedev<suffix>` / `referral-func` / your tag |
| Container | Authentication | Managed identity > `id-referralintake-func-dev` |
| **Networking** | Enable public access | **Off** |
| **Networking** | Enable network injection | **On** |
| **Networking** | Virtual network | `vnet-referralintake-spoke-dev` |
| **Networking** | Inbound: Enable private endpoints | **On** > **+ Add** (below) |
| **Networking** | Outbound: Enable VNet integration | **On** > Subnet `snet-functions` |
| Monitoring | Application Insights | `appi-referralintake-dev` |

**Inbound private endpoint (on the VNet):**

| Field | Value |
|---|---|
| Name | `pe-func-referralintake-dev` |
| Subnet | `snet-private-endpoints` |
| Integrate with private DNS zone | **Yes** > `privatelink.azurewebsites.net` |

**Review + create > Create.** If the wizard rejects the storage account because key access is disabled, record it as a portal gap (see appendix); do not turn on keys.

**After create:**
1. Link `privatelink.azurewebsites.net` to the hub ([how](#24-peering)).
2. **Settings > Identity > User assigned > + Add** `id-referralintake-func-dev` (if not already attached).
3. **Settings > Networking > Outbound traffic configuration**: **Outbound internet traffic** routed through VNet = On; **Container image pull** through VNet = On.
4. **Settings > Configuration > General settings**: HTTPS Only On, Min TLS 1.2, FTP state Disabled, Always on On.
5. **Settings > Scale out**: Always ready instances 1, Maximum burst 3.
6. **Deployment > Deployment Center**: Registry source ACR, image `referral-func`, Authentication **Managed identity** > `id-referralintake-func-dev` > **Save**.
7. **Settings > Environment variables > App settings**: add the [app settings](#16-app-settings) (Function identity client ID) **plus** the Function-only table. Delete any generated `AzureWebJobsStorage` connection string or `DOCKER_REGISTRY_SERVER_USERNAME/PASSWORD`. **Apply.**
8. **App registration > Authentication > Web > Add URI** `https://<function-hostname>/.auth/login/aad/callback` > **Save**.
9. **Function > Settings > Authentication > Add identity provider > Microsoft**: same values as 14.4, except **Unauthenticated requests = HTTP 401**.
10. **Overview > Restart.**

**Check:** **Overview > Functions** lists the queue-triggered function.

---

## 16. App settings

Used by the API container (14.3) and the Function App (15). Use the matching identity's client ID.

| Name | Value |
|---|---|
| `DATABASE_URL` | `mssql+pyodbc://@<sql-server>.database.windows.net/sqldb-referralintake?driver=ODBC+Driver+18+for+SQL+Server&authentication=ActiveDirectoryMsi&UID=<identity-client-id>` |
| `AZURE_CLIENT_ID` | API: ACA identity client ID; Function: Func identity client ID |
| `STORAGE_ACCOUNT_URL` | `https://streferralindev<suffix>.blob.core.windows.net` |
| `QUEUE_ACCOUNT_URL` | `https://streferralindev<suffix>.queue.core.windows.net` |
| `QUEUE_NAME` | `referral-jobs` |
| `INCOMING_CONTAINER` | `incoming` |
| `PROCESSING_CONTAINER` | `processing` |
| `FAILED_CONTAINER` | `failed` |
| `ARCHIVE_CONTAINER` | `archive` |
| `LOGIC_APP_URL` | Logic App HTTP URL (secret) |
| `DOCUMENT_INTELLIGENCE_ENDPOINT` | Document Intelligence endpoint |
| `CONTENT_UNDERSTANDING_ENDPOINT` | AI Services endpoint |
| `CONTENT_UNDERSTANDING_ANALYZER` | `referralIntake` |
| `CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT` | `gpt-5.2` |
| `CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` |
| `LOCAL_MOCK_IDENTITY` | `false` |
| `ALLOW_LOCAL_MOCK_EXTRACTION` | `false` |

Function App only:

| Name | Value |
|---|---|
| `FUNCTIONS_WORKER_RUNTIME` | `python` |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` |
| `DOCKER_REGISTRY_SERVER_URL` | `https://<acr-login-server>` |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE` | `false` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | App Insights connection string |
| `AzureWebJobsStorage__accountName` | `streferralindev<suffix>` |
| `AzureWebJobsStorage__credential` | `managedidentity` |
| `AzureWebJobsStorage__clientId` | Func identity client ID |

---

## 17. Event subscription

Portal: **Event Grid System Topics > evgt-referralintake-dev > + Event Subscription**.

| Tab | Field | Value |
|---|---|---|
| Basics | Name / Event schema | `referral-incoming` / Event Grid Schema |
| Basics | Filter to event types | **Blob Created** only |
| Basics | Endpoint type / Endpoint | **Storage Queues** / `streferralindev<suffix>` > existing queue `referral-jobs` |
| Basics | Managed identity for delivery | **System assigned** |
| Basics | Queue message time to live | 7 days |
| Filters | Enable subject filtering > Subject begins with | `/blobServices/default/containers/incoming/blobs/` |
| Additional features | Max event delivery attempts / Event time to live | 10 / 1 day (1440 min) |

**Create.**

---

## 18. Diagnostics, alert, and private monitoring

### 18.1 Diagnostics and alert

1. **Function App > Monitoring > Diagnostic settings > + Add**: `diag-func-referralintake-dev`, check **FunctionAppLogs** and **AllMetrics**, Send to `log-referralintake-dev`.
2. **Logic App > Monitoring > Diagnostic settings > + Add**: `diag-logic-referralintake-notification-dev`, **allLogs** and **AllMetrics**, same workspace.
3. **log-referralintake-dev > Alerts > + Create > Alert rule** > Signal **Custom log search**, query:

```kusto
union isfuzzy=true
    (FunctionAppLogs | where Level == "Error" | project TimeGenerated),
    (ContainerAppConsoleLogs_CL | where Log_s has "failed during processing" | project TimeGenerated)
```

   Measure **Table rows**, Count, Greater than 0, every 5 min, lookback 15 min. Details: severity 2, name `alert-referralintake-failed-jobs-dev`, display name `Referral processing failures`, auto-resolve on. Add an action group only if you want notifications.

### 18.2 Make monitoring private-only

Do this after logs from both apps appear in `log-referralintake-dev`. App telemetry already flows over the AMPLS endpoint from step 4; diagnostic settings use a Microsoft backbone channel and are not affected by these switches.

1. **Move Container Apps logs onto a diagnostic setting.** The environment's **Azure Log Analytics** destination may not reach a private-only workspace. **cae-referralintake-dev > Monitoring > Logging options** > Logs destination **Azure Monitor** > **Save**. Then **Monitoring > Diagnostic settings > + Add**: `diag-cae-referralintake-dev`, check **ContainerAppConsoleLogs** and **ContainerAppSystemLogs**, Send to `log-referralintake-dev`, destination table **Resource specific** > **Save**.
2. **Update the alert** from 18.1: edit its query and change the second line to `(ContainerAppConsoleLogs | where Log has "failed during processing" | project TimeGenerated)`. Logs now land in that table instead of `ContainerAppConsoleLogs_CL`.
3. **log-referralintake-dev > Settings > Network isolation**: **Accept data ingestion from public networks not connected through a Private Link Scope** = **No**; **Accept queries from public networks not connected through a Private Link Scope** = **No** > **Save**.
4. **appi-referralintake-dev > Configure > Network Isolation**: same two settings = **No** > **Save**.

**Check:** from the jumpbox, **log-referralintake-dev > Logs** returns new `FunctionAppLogs` and `ContainerAppConsoleLogs` rows. From outside the VNet, queries are refused; this is expected.

---

## 19. Test end to end

From the jumpbox browser:

1. **Private endpoints** (search the blade): nine endpoints (the eight service endpoints plus `pe-ampls-referralintake-dev`), all **Approved**, IPs in `10.21.3.0/24`.
2. **Container App > Monitoring > Log stream** (`api`): startup completes, analyzer setup succeeds.
3. **Storage > Containers > incoming > Upload** a new file from [`samples`](../samples/README.md).
4. **Event Grid topic > Metrics**: Delivered events > 0. **Storage > Queues** `referral-jobs-poison` stays empty.
5. Open the web app URL > review queue > approve or return the referral.
6. **Logic App > Runs history** shows a run; the file is in `archive` (approved) or `failed`.

---

## Appendix

### Who does what

| Task | Needs |
|---|---|
| Register providers, create the resource group | Subscription Contributor or Owner (admin) |
| Create resources in this guide | Contributor on `rg-referralintake` |
| Role assignments (IAM steps) | Owner, User Access Administrator, or Role Based Access Control Administrator on the resource group |
| App registration and redirect URIs | Entra Application Administrator or owner of the app |
| SQL Query Editor step | Member of the SQL admin Entra group |
| Storage/Key Vault data steps | Data role on the resource **and** the jumpbox browser (private network) |
| Defender plans | Subscription security admin |

Contributor cannot do role assignments. Do not grant Owner just to make a wizard succeed.

### Defender for Cloud (optional, subscription-wide)

The automated deployment turns on Defender Standard for App Services, Containers, Key Vaults, SQL servers, Storage, and Virtual machines. Portal: **Microsoft Defender for Cloud > Environment settings > subscription > Defender plans**. This affects billing for the whole subscription; agree it with the security owner.

Defender for Storage malware scanning can create its own Event Grid system topic on the storage account. Azure allows only one, so create step 8 before turning on Defender. If one already exists, see [the deployment caveat](deployment.md#event-grid-and-defender-for-storage-share-one-slot); do not delete Defender's topic.

### Things the portal may not let you do

Record these as gaps rather than working around them with public access or keys:

- **Images**: the portal cannot build the three images (step 12).
- **Function App storage with keys disabled**: some wizard versions require key access; the template uses identity-based `AzureWebJobsStorage__*` settings.
- **Storage exceptions** (step 8) can be hidden while public access is disabled.
- **ACR**: managed-identity pulls need the registry's ARM-audience token setting enabled (default on new registries).
- **App Insights local auth disabled** and **SQL restrict outbound networking** may not be exposed in the portal.
- **Foundry** may ask you to create a project before deploying models; deploy into the same `ai-referralintake-dev-<suffix>` resource.
- **Container Apps second container**: if the revision editor cannot add `api`, the app cannot run as designed.

### Troubleshooting

| Symptom | Check |
|---|---|
| `AuthorizationFailed ... register/action` | Providers not registered; subscription admin does step 1 |
| Can't add role assignment | You need an IAM-capable role (see table above) |
| Storage/Key Vault blade says access denied | Use the jumpbox browser; confirm your data role and hub DNS link |
| Image pull fails | AcrPull on the identity, identity attached, `privatelink.azurecr.io` records, Function image-pull through VNet |
| Web URL fails from jumpbox | ACA default-domain zone + wildcard A record + hub link |
| API won't start | SQL users created (step 9), `DATABASE_URL` client ID, SQL zone hub/spoke links |
| Blob uploads not processed | Event subscription, topic sender role, storage trusted-services exception, Function running |
| No email/Teams message | The Logic App only records events; add a connector action yourself |
| Logic App trigger returns 401/403 | Trigger IP restriction (13 option A) must match the NAT gateway IP; NAT gateway attached to `snet-aca` and `snet-functions` |
| Logs/App Insights blade says "Unable to connect" on the jumpbox | Edge > **Settings > Privacy, search, and services > Site permissions > Local network access** > allow `https://portal.azure.com`; AMPLS zones linked to the hub |
| Telemetry stopped after 18.2 | AMPLS endpoint Approved, five monitor zones linked to spoke, Container Apps logging moved to a diagnostic setting |

### Source templates

[`main.bicep`](../infra/main.bicep), [`network.bicep`](../infra/modules/network.bicep), [`bastion.bicep`](../infra/modules/bastion.bicep), [`jumpbox.bicep`](../infra/modules/jumpbox.bicep), [`observability.bicep`](../infra/modules/observability.bicep), [`identity-security.bicep`](../infra/modules/identity-security.bicep), [`data.bicep`](../infra/modules/data.bicep), [`ai.bicep`](../infra/modules/ai.bicep), [`registry.bicep`](../infra/modules/registry.bicep), [`integration.bicep`](../infra/modules/integration.bicep), [`compute.bicep`](../infra/modules/compute.bicep), [`eventing.bicep`](../infra/modules/eventing.bicep), [`defender.bicep`](../infra/modules/defender.bicep), [`scripts/bootstrap-sql.sql`](../scripts/bootstrap-sql.sql).
