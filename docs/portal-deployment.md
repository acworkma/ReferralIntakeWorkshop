# Manual Azure portal deployment

This runbook recreates the referral intake workshop by creating and configuring individual resources in the [Azure portal](https://portal.azure.com). Start with the [architecture diagram](architecture.md). The [Bicep deployment guide](deployment.md) remains the automated alternative.

**Boundary:** this is a portal-UI-only resource configuration guide, not a claim that the repository can be built entirely inside the Azure portal. It contains no CLI, PowerShell, Cloud Shell, or template-deployment steps. Entering SQL or workflow JSON into a supported portal editor is part of the UI procedure.

## Read this before creating resources

| Task | Portal-only status | What you need |
|---|---|---|
| Create resource group, network, managed identities, data services, IAM grants, and hosting | Supported in portal UI | Correct permissions and available service capacity |
| Build and publish this repository's three container images | External prerequisite | An authorized build team/process must supply the actual images in your registry. Creating ACR or selecting a Functions base image does not build this application. |
| Initialize the private SQL database | Supported through portal Query Editor from a privately connected browser | SQL administrator opens the portal inside the jumpbox, or from an existing privately connected workstation |
| Deploy AI models | Microsoft Foundry portal UI | Open the existing AI resource in Foundry; do not accidentally create a second account. If only `portal.azure.com` is permitted, this is a separate portal dependency. |
| Configure Content Understanding defaults and custom analyzer | Application startup, not a separate operator script | The real API image configures them using its managed identity; verify the startup logs |
| Match every template property in every portal version | Not guaranteed | Where the required control is absent, record a configuration gap and stop that step. Do not silently substitute public access, keys, or a different architecture. |

**Do not call the application deployed until real images, SQL permissions, AI initialization, private DNS, authentication, and a synthetic-document test all work.** Placeholder containers are not a working referral pipeline. This guide was checked against source and Microsoft Learn, not exercised as a live customer portal deployment.

Use synthetic samples only; no real patient, personal, customer, or production data. Premium Functions, Premium ACR, SQL, AI models/transactions, Bastion, private endpoints, logs, the VM, and running containers incur charges. Defender plans can change billing for other resources in the subscription.

### Who does what

| Responsibility | Required authority |
|---|---|
| Register providers; create resource group | Subscription-level permission for those actions; subscription Contributor includes them |
| Grant deployment access and runtime IAM roles | Owner, RBAC Administrator, or another authorized role at the relevant scope; Contributor alone cannot assign roles |
| Create/manage the app registration and enterprise application | Authorized Entra application creator/owner or application administrator, subject to tenant policy; Azure Owner alone is insufficient |
| Create/configure workload resources | Contributor on the resource group, subject to policy, locks, quotas, and cross-resource access |
| Run database bootstrap | Member of the SQL Entra administrator group, or an appropriately authorized database principal; Azure Contributor is not a database role |
| Browse private storage/vault data | Private network reachability plus the relevant data-plane role; Azure Contributor alone is insufficient |

For the simplest manual setup, have the appropriate administrators available for their steps rather than granting the operator subscription Owner or inventing a custom role. Portal wizards sometimes try to create IAM assignments automatically; have the access administrator preassign the roles in section 8.

Sources: [provider registration](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types), [Contributor and access-management roles](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/privileged), [Entra application delegation](https://learn.microsoft.com/entra/identity/role-based-access-control/delegate-app-roles).

### Reusing an existing environment

Before each **Create**, search the target resource group for the intended resource. Reuse it only after checking its type, region, SKU, identities, network, and security settings. Check for an existing role/principal/scope assignment before adding another. Preserve unrelated redirects, secrets, application settings, and resources. Do not reset the VM password or replace deployed image tags as a side effect of setup.

An existing resource with an incompatible immutable setting is a blocker, not permission to delete or recreate it. A soft-deleted vault or globally reserved name can also prevent creation. Record the issue and ask the owning administrator to resolve it.

## 1. Fill in the deployment worksheet

These are the values in [`infra/main.bicepparam`](../infra/main.bicepparam), not generic Azure wizard defaults. Names below assume `workloadName=referralintake` and `environmentName=dev`. Replace `<suffix>` with one stable lowercase, 3-8-character alphanumeric value.

| Input | Value |
|---|---|
| Tenant and subscription | Customer's approved tenant and subscription; confirm in portal directory/subscription filter |
| Resource group | `rg-referralintake` |
| Primary region | East US 2 (`eastus2`) |
| SQL region | Central US (`centralus`); the root template's fallback default is different, so use the parameter-file value |
| Content Understanding region | West US 3 (`westus3`) |
| Unique suffix | `<suffix>`; record once and reuse throughout |
| SQL administration | Existing Entra group display name and object ID |
| Jumpbox secret readers | Existing approved group/user object ID, or omit this optional grant |
| VM credentials | Username `azureadmin`; password in an approved secret store, not this worksheet |
| Tags | `workload=referralintake`, `environment=dev`, `managedBy=portal` |

The portal path deliberately uses `managedBy=portal` rather than the templates' `managedBy=bicep` tag.

### Resource inventory and dependency order

| Stage | Resources / default names |
|---|---|
| Prerequisites | Resource group; Entra app `app-referralintake-dev` and its enterprise application |
| Network | `vnet-referralintake-hub-dev`, `vnet-referralintake-spoke-dev`; three NSGs; five subnets; two peerings; seven service DNS zones |
| Administration | `pip-bastion-referralintake-dev`, `bas-referralintake-dev`; optional `nic-referralintake-jump-dev`, `vm-referralintake-jump-dev` and managed OS disk |
| Monitoring | `log-referralintake-dev`, `appi-referralintake-dev`, `alert-referralintake-failed-jobs-dev` |
| Identities | `id-referralintake-func-dev`, `id-referralintake-aca-dev` |
| Data | `kv-referralintake-<suffix>`; `streferralindev<suffix>`; `sql-referralintake-dev-centra-<suffix>`; `sqldb-referralintake` |
| Event source | `evgt-referralintake-dev` with a system-assigned identity |
| AI | `doc-referralintake-dev-<suffix>`; `ai-referralintake-dev-<suffix>`; two model deployments |
| Registry | `crreferralintakedev<suffix>` and three image repositories |
| Private endpoints | Eight endpoint resources, associated NICs, and DNS zone groups; see section 7 |
| Business workflow | `logic-referralintake-notification-dev` with system-assigned identity |
| Hosting | `cae-referralintake-dev`, `ca-referralintake-web-dev` with two containers; `asp-referralintake-func-dev`, `func-referralintake-dev` |
| Final wiring | IAM grants, event subscription `referral-incoming`, ACA environment DNS zone/record/links, Entra callbacks, SQL users, diagnostics |
| Subscription settings | Defender Standard plans: AppServices, Containers, KeyVaults, SqlServers, StorageAccounts, VirtualMachines |

The storage formula truncates workload to ten characters, environment to three, then the whole name to 24: `st` + `referralin` + `dev` + suffix. Do not use the full workload name for storage. SQL's region fragment is the first six characters of `centralus`: `centra`.

Record nonsecret values as resources are created:

| Worksheet key | Where to obtain it |
|---|---|
| `TENANT_ID`, `ENTRA_CLIENT_ID` | App registration Overview |
| `FUNC_CLIENT_ID`, `FUNC_PRINCIPAL_ID`, `FUNC_IDENTITY_RESOURCE_ID` | Function managed identity Overview / Properties |
| `ACA_CLIENT_ID`, `ACA_PRINCIPAL_ID`, `ACA_IDENTITY_RESOURCE_ID` | Container Apps managed identity Overview / Properties |
| Storage name, SQL server FQDN | Respective Overview pages |
| AI endpoints | Each account's endpoint page; use its custom-subdomain endpoint, not a guessed regional URL |
| `ACR_LOGIN_SERVER` | ACR Overview; use the actual value, including any portal-generated domain label |
| `ACA_DEFAULT_DOMAIN`, `ACA_STATIC_IP` | Container Apps environment Overview / Properties |
| Web FQDN, Function hostname | Container App Application URL and Function Overview default hostname |
| Application Insights connection string | Application Insights Overview; handle as operational configuration |

Keep the signed Logic App callback URL and VM password in approved secret handling, not shared notes or screenshots.

### Navigation

Follow the numbered sections in order, returning to the private-endpoint and IAM sections as each target becomes available. The final Function endpoint cannot be created before the Function exists.

| Prepare | Provision | Finish |
|---|---|---|
| [Administrator prerequisites](#2-administrator-prerequisites) | [Identities, vault, storage and topic](#5-identities-vault-storage-and-early-event-source) | [Container Apps](#11-container-apps-environment-private-ingress-and-webapi) |
| [Network foundation](#3-network-foundation) | [SQL, AI and registry](#6-sql-ai-and-registry) | [Function App](#12-function-app-and-private-networking) |
| [Private administration and monitoring](#4-private-administration-and-monitoring) | [Private endpoints](#7-private-endpoints-and-dns-wiring) | [Authentication](#13-entra-authentication-and-callbacks) |
| | [Runtime IAM grants](#8-administrator-runtime-iam-grants) | [Application settings](#14-complete-application-settings) |
| | [SQL initialization](#9-initialize-sql-through-the-portal) | [Event wiring, diagnostics and Defender](#15-final-event-wiring-diagnostics-and-defender) |
| | [Logic App](#10-consumption-logic-app) | [Readiness checks](#16-verify-a-working-deployment) |

## 2. Administrator prerequisites

### Register the resource providers

In **Subscriptions > target subscription > Resource providers**, search each namespace and select **Register** only where necessary:

| Namespace | Service |
|---|---|
| `Microsoft.App` | Container Apps |
| `Microsoft.Web` | Functions and hosting plan |
| `Microsoft.Storage` | Blob and Queue Storage |
| `Microsoft.EventGrid` | System topic and event subscription |
| `Microsoft.Sql` | SQL server/database |
| `Microsoft.CognitiveServices` | AI accounts and models |
| `Microsoft.KeyVault` | Vault and secret |
| `Microsoft.ManagedIdentity` | User-assigned identities |
| `Microsoft.Network` | Network, DNS, Bastion and private endpoints |
| `Microsoft.OperationalInsights` | Log Analytics |
| `Microsoft.Insights` | Application Insights, alerts and diagnostics |
| `Microsoft.Security` | Defender configuration |
| `Microsoft.ContainerRegistry` | ACR |
| `Microsoft.Logic` | Logic App |
| `Microsoft.Compute` | Jumpbox |

`Microsoft.Resources` and `Microsoft.Authorization` are also used but registered by default. Some Azure wizards can request supporting providers; handle any specific additional request with the subscription administrator rather than assigning the deployer broader rights. A provider can remain **Registering** while individual regions are ready; this state alone does not prove deployment is blocked.

### Resource group and operator access

Open **Resource groups > Create**, select the worksheet subscription, name, and primary region, then **Review + create**. For an existing group, verify it instead.

The access administrator opens **resource group > Access control (IAM) > Add role assignment**, selects **Contributor**, then the approved operator/CI principal, and completes **Review + assign**. Do not grant User Access Administrator or Owner just to make the wizards succeed. Runtime grants are a separate step.

### App registration

In **Microsoft Entra ID > App registrations > New registration**:

1. Name it `app-referralintake-dev`; select **Accounts in this organizational directory only**.
2. Register and record the application/client ID and tenant ID.
3. Under **Expose an API**, set Application ID URI to `api://<ENTRA_CLIENT_ID>`.
4. Under **Authentication**, enable **ID tokens (implicit and hybrid flows)**, leave access-token implicit issuance disabled, and save. Callback URIs are added in section 13.
5. In **Enterprise applications**, verify the corresponding service principal exists in the tenant. Do not adopt a similarly named application from another deployment.

For an existing registration, use its known client ID, inspect tenant/account type and ID-token settings, and preserve existing callbacks. The manual path does not require adding a client secret; do not use an authentication wizard that creates a different registration or secret by default.

## 3. Network foundation

Source of truth: [`network.bicep`](../infra/modules/network.bicep).

### VNets and subnets

Search **Virtual networks > Create**. Create both VNets in East US 2 and the target resource group. Remove any wizard-created default subnet if it is unused and not part of this design.

| VNet / address space | Subnet | Address prefix | Delegation / NSG |
|---|---|---|---|
| Hub `10.20.0.0/16` | `AzureBastionSubnet` | `10.20.1.0/26` | None / Bastion NSG |
| Hub | `snet-jumpbox` | `10.20.2.0/24` | None / hub NSG |
| Spoke `10.21.0.0/16` | `snet-aca` | `10.21.0.0/23` | `Microsoft.App/environments` / workload NSG |
| Spoke | `snet-functions` | `10.21.2.0/24` | `Microsoft.Web/serverFarms` / workload NSG |
| Spoke | `snet-private-endpoints` | `10.21.3.0/24` | None / workload NSG; private endpoint network policies **Disabled** |

Set delegation and NSG under each VNet's **Subnets > subnet** page after creating the NSGs. Check address overlap with customer networks before proceeding.

**Environment compatibility:** the delegated ACA subnet above is for a workload-profiles environment. Select that environment type with the Consumption workload profile when creating the portal environment. Microsoft's legacy Consumption-only environment requires an undelegated subnet. Do not combine that legacy choice with this delegation. The repository does not explicitly declare workload profiles, so portal defaults are not proof of identical environment configuration; record the selected environment type in the worksheet.

### Network security groups

Create the three groups through **Network security groups > Create**, then **Inbound security rules / Outbound security rules > Add**. All source ports are `*`; `Any` below means `*`. Use **Service Tag** for named tags such as Internet, GatewayManager, AzureCloud and AzureLoadBalancer.

| NSG | Direction | Priority / rule name | Source | Destination | Protocol / destination ports | Action |
|---|---|---|---|---|---|---|
| `nsg-referralintake-hub-dev` | In | 200 `AllowBastionRdpInbound` | `10.20.1.0/26` | Any | TCP / 3389 | Allow |
| Hub | In | 4096 `DenyInternetInbound` | Internet | Any | Any / Any | Deny |
| `nsg-referralintake-workload-dev` | In | 100 `AllowAzureLoadBalancer` | AzureLoadBalancer | Any | Any / Any | Allow |
| Workload | In | 4096 `DenyInternetInbound` | Internet | Any | Any / Any | Deny |
| `nsg-referralintake-bastion-dev` | In | 120 `AllowHttpsInbound` | Internet | Any | TCP / 443 | Allow |
| Bastion | In | 130 `AllowGatewayManagerInbound` | GatewayManager | Any | TCP / 443 | Allow |
| Bastion | In | 140 `AllowAzureLoadBalancerInbound` | AzureLoadBalancer | Any | TCP / 443 | Allow |
| Bastion | In | 150 `AllowBastionHostCommunicationInbound` | VirtualNetwork | VirtualNetwork | Any / 8080,5701 | Allow |
| Bastion | In | 4096 `DenyAllInbound` | Any | Any | Any / Any | Deny |
| Bastion | Out | 100 `AllowSshRdpOutbound` | Any | VirtualNetwork | Any / 22,3389 | Allow |
| Bastion | Out | 110 `AllowAzureCloudOutbound` | Any | AzureCloud | TCP / 443 | Allow |
| Bastion | Out | 120 `AllowBastionCommunicationOutbound` | VirtualNetwork | VirtualNetwork | Any / 8080,5701 | Allow |
| Bastion | Out | 130 `AllowHttpOutbound` | Any | Internet | Any / 80 | Allow |

Leave Azure's built-in default rules in place. The template does not add an outbound deny-all rule or a firewall; do not invent one. See [required Bastion NSG rules](https://learn.microsoft.com/azure/bastion/bastion-nsg).

In **hub VNet > Peerings > Add**, configure local `peer-to-spoke` and remote `peer-to-hub`, selecting the spoke. Allow virtual network access and forwarded traffic in both directions. Do not enable gateway transit. Verify both peerings show **Connected**.

### Service private DNS zones

Search **Private DNS zones > Create** and create these global zones in the group:

| Zone | Used by |
|---|---|
| `privatelink.blob.core.windows.net` | Storage Blob |
| `privatelink.queue.core.windows.net` | Storage Queue |
| `privatelink.database.windows.net` | SQL |
| `privatelink.vaultcore.azure.net` | Key Vault |
| `privatelink.azurecr.io` | ACR |
| `privatelink.cognitiveservices.azure.com` | Both AI accounts |
| `privatelink.azurewebsites.net` | Function |

For each zone, open **Virtual network links > Add**, name `link-vnet-referralintake-spoke-dev`, choose the spoke, and leave autoregistration disabled.

**Jumpbox DNS addition:** also link each service zone to the hub, with autoregistration disabled, if the jumpbox uses Azure-provided DNS. The current network template links these seven zones only to the spoke. Peering does not extend private-zone visibility to the hub. These extra hub links are an explicit manual-path correction required for jumpbox data access, not an assertion that the template already creates them. If central DNS forwarding already provides resolution, have the network owner confirm the equivalent configuration instead.

## 4. Private administration and monitoring

### Bastion and optional jumpbox

1. Search **Public IP addresses > Create**. Create `pip-bastion-referralintake-dev` in East US 2, **Standard**, IPv4, **Static**, with regional scope.
2. Search **Bastions > Create**. Create `bas-referralintake-dev`, **Basic**, using the hub's `AzureBastionSubnet` and that public IP. Do not use Developer SKU for this design.
3. If an approved private workstation is not available, create **Virtual machine** `vm-referralintake-jump-dev`, East US 2, **Windows 11 Pro 25H2 x64** corresponding to image `MicrosoftWindowsDesktop/windows-11/win11-25h2-pro`, latest available version; size `Standard_D2as_v5`, Trusted launch, Premium SSD LRS OS disk. Verify Windows client licensing eligibility. If that image/size is unavailable, obtain an approved substitute and record the deviation rather than guessing.
4. Set username `azureadmin` and the approved password. Select the hub and `snet-jumpbox`; **Public IP: None**, **Public inbound ports: None**. Use the existing hub NSG, not a generated RDP-from-Internet rule. Enable the system-assigned identity and automatic OS updates. Where creation exposes the NIC name, use `nic-referralintake-jump-dev`; otherwise record its generated name. The template's computer name is `refjump`; if the wizard derives a different hostname, record that nonfunctional naming difference.
5. Verify the VM has **no public IP**. Open **VM > Connect > Bastion**, authenticate, and open the Azure portal in the VM's browser. Use this browser for later storage, vault, SQL and application data-plane operations. Do not use VM Run Command to smuggle scripts into this UI-only procedure.

If skipping the VM, record the existing private workstation/network path that replaces it. The template creates a system-assigned VM identity but assigns no runtime roles to it.

### Monitoring foundation

Search **Log Analytics workspaces > Create**: `log-referralintake-dev`, East US 2, retention **30 days**. Under **Properties**, use resource-or-workspace permissions for log access, matching `enableLogAccessUsingOnlyResourcePermissions=true`. The template leaves public ingestion and query access enabled; it does not deploy Azure Monitor Private Link.

Search **Application Insights > Create**: `appi-referralintake-dev`, East US 2, workspace-based, select the existing workspace. Disable local authentication in its properties where exposed and record the connection string. If that control is absent, mark the `DisableLocalAuth=true` parity gap rather than assuming it is enabled. Diagnostics for Function and Logic App are added after their creation.

## 5. Identities, vault, storage, and early event source

### User-assigned identities

Search **Managed Identities > Create** twice in the target group/region:

- `id-referralintake-func-dev`
- `id-referralintake-aca-dev`

Record **client ID**, **principal/object ID**, and **Azure resource ID** separately. Client IDs are used in application settings; object IDs are used for IAM and SQL identity resolution; resource IDs are used for identity attachment.

### Key Vault

Search **Key vaults > Create**: `kv-referralintake-<suffix>`, East US 2, Standard. Select **Azure role-based access control**, soft-delete retention **90 days**, purge protection **enabled**, and public network access **disabled**. Do not switch to access policies to avoid assigning roles.

Create the vault private endpoint in section 7 before managing its secrets from the jumpbox browser. The templates persist `jumpbox-admin-password`; create it through **Objects > Secrets > Generate/Import** using the same actual VM password. The human creating that secret needs temporary **Key Vault Secrets Officer** or equivalent secret-write access on this vault, granted by the access administrator. This manual data-plane permission is separate from the template's ARM secret creation and from the read-only jumpbox grant. Remove temporary access according to customer policy after setup.

If omitting the jumpbox, omit this secret and its optional reader grant. Changing a vault secret does not change the VM password.

### Storage

Search **Storage accounts > Create** with these explicit settings:

| Setting | Value |
|---|---|
| Name | `streferralindev<suffix>` |
| Region, kind, performance | East US 2; StorageV2 / general-purpose v2; Standard |
| Redundancy | ZRS |
| Secure transfer required / minimum TLS | Enabled / 1.2 |
| Blob anonymous access | Disabled |
| Storage account key access | Disabled |
| Default authentication in portal | Microsoft Entra authorization |
| Public network access | Disabled |
| Hierarchical namespace | Disabled |
| Blob soft delete and container soft delete | Enabled, 7 days each |

Do not enable shared keys to make the portal browser work. After private endpoints and the operator's data roles are ready, use the jumpbox browser, select **Data storage > Containers**, and create private containers `incoming`, `processing`, `failed`, `archive`. Under **Queues**, create `referral-jobs` and `referral-jobs-poison`.

**Early system topic:** immediately after storage creation, search **Event Grid System Topics > Create**, choose type **Storage Accounts**, the worksheet subscription/group/storage account, name `evgt-referralintake-dev`. Enable its **Identity > System assigned > On**, save, and record its principal ID. Do not create the event subscription yet.

Azure permits only one system topic per storage source. In a manual deployment, Defender can claim that topic before this step; speed is not a guarantee. If one already exists, identify its owner with the administrator and consult [the existing deployment caveat](deployment.md#event-grid-and-defender-for-storage-share-one-slot). Do not delete Defender's topic or subscriptions. Resolving a collision is an explicit design/administrator decision.

Source: [manage system topics in the portal](https://learn.microsoft.com/azure/event-grid/create-view-manage-system-topics).

## 6. SQL, AI, and registry

### SQL server and database

Search **SQL databases > Create**. Create database `sqldb-referralintake` and logical server `sql-referralintake-dev-centra-<suffix>` in **Central US**. Select **Microsoft Entra-only authentication**, set the worksheet SQL administrator group, and choose **Standard S0**, not serverless/free or SQL Managed Instance.

Disable public network access; minimum TLS **1.2**. Disable read scale-out and zone redundancy for the database, matching the template. The server template also sets **restrict outbound network access** enabled; check the server's outbound networking controls and record a parity gap if the portal does not expose this setting. Do not invent outbound allow rules or enable public SQL login for setup.

Create the SQL private endpoint in the spoke's private-endpoint subnet in East US 2; the endpoint can be in a different region from the SQL server. Bootstrap the database in section 9 before starting the real API.

### AI accounts and model deployments

1. Search **Document Intelligence > Create**. Name `doc-referralintake-dev-<suffix>`, East US 2, **S0**. Its resource kind must be `FormRecognizer`; configure the corresponding custom subdomain.
2. Create the [Microsoft Foundry resource for Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/how-to/create-multi-service-resource), name `ai-referralintake-dev-<suffix>`, **West US 3**, **S0**. Verify the Azure account kind is `AIServices`, not a standalone OpenAI account or a hub with a different endpoint.
3. On both accounts, disable public network access, set network default action Deny, and disable local/key authentication where the portal exposes it. The required property is `disableLocalAuth=true`; if unavailable, record the UI parity gap. The application uses Entra tokens, not API keys.
4. Create both private endpoints in section 7. Record each custom-subdomain endpoint.
5. Open the **existing** Content Understanding resource in the linked **Microsoft Foundry portal**. In the model deployment/catalog UI, deploy these **into that same account**:

| Deployment name | Model / version | Deployment type | Template capacity |
|---|---|---|---|
| `gpt-5.2` | `gpt-5.2` / `2025-12-11` | Global Standard | 50 |
| `text-embedding-3-large` | `text-embedding-3-large` / `1` | Global Standard | 50 |

Deploy sequentially, waiting for the first to succeed. The UI can display throughput in model-specific units rather than raw ARM capacity; verify the equivalent quota allocation instead of interpreting 50 as a universal requests-per-minute value. Confirm the exact model/version and Global Standard capacity are available in the customer's account/region. A regional Standard embedding deployment is not equivalent. If unavailable, stop and obtain an approved model/configuration change; this guide does not change the application defaults.

The current [Foundry model deployment instructions](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/deploy-foundry-models) use a Foundry project. The Bicep reference does not create one. If the customer's UI requires a project to reach model management, record that additional portal dependency and verify the deployments still belong to the intended `AIServices` account. Do not create a replacement account or change endpoints without reconciling the worksheet.

No separate custom analyzer script is needed. The real API's [`analyzer.py`](../api/referral/analyzer.py) configures the model defaults and `referralIntake` analyzer at startup over private networking. This is application execution, not a portal capability; the UI provisioned accounts alone cannot replace it.

### Container registry and the external image prerequisite

Search **Container registries > Create**: `crreferralintakedev<suffix>`, East US 2, **Premium**. Select **RBAC Registry Permissions**, not **RBAC Registry + ABAC Repository Permissions**, to retain the template's `AcrPull` role semantics. The current Azure quickstart defaults can differ.

Leave admin user and anonymous pull disabled; enable the dedicated data endpoint. Under networking retain the approved initial **public access enabled** setting from the parameter file, with trusted Azure services bypass, and add its private endpoint. Public ACR access still requires identity authorization. Once an approved private image-build/publishing path exists, the administrator can disable public access. Do not disable it prematurely if the build team's route depends on it.

Match the template's untagged-manifest retention policy: enabled, **7 days**; quarantine disabled. Record the actual login server; do not construct it from the registry name if the portal added a domain-name-label hash.

**Stop here for application rollout if these images do not exist.** The build team must supply Linux/amd64 images from the same source revision, with immutable tags:

| ACR repository | Source provided to the build team |
|---|---|
| `referral-web` | [`web/Dockerfile`](../web/Dockerfile), build context `web` |
| `referral-api` | [`api/Dockerfile`](../api/Dockerfile), build context repository root |
| `referral-func` | [`functions/Dockerfile`](../functions/Dockerfile), build context repository root |

In **ACR > Repositories**, verify all three repositories/tags before use. Portal resource creation is not a source build; this repository does not supply a ready-made image in a public registry. This runbook intentionally does not redirect to Cloud Shell, GitHub Actions, or an unverified "Build" button. See [ACR portal quickstart](https://learn.microsoft.com/azure/container-registry/container-registry-get-started-portal), which uses external Docker commands for publishing images.

Managed-identity pulls also require ACR to accept ARM-audience tokens. This is normally enabled for a new registry; if an existing registry disables it and the portal lacks a control, record a blocker for its owner rather than enabling registry passwords. See [managed-identity image pulls](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull).

## 7. Private endpoints and DNS wiring

After each target resource exists, open **target > Networking > Private endpoint connections > Create**, or search **Private endpoints > Create**. Select the target subscription/group/resource, the subresource below, endpoint region East US 2, spoke VNet and `snet-private-endpoints`. Choose **Integrate with private DNS zone**, select the existing zone, and create DNS zone group `default`. Approve the connection if it is not automatically approved.

| Endpoint name | Target | Subresource | Existing DNS zone |
|---|---|---|---|
| `pe-streferralindev<suffix>-blob` | Storage | `blob` | `privatelink.blob.core.windows.net` |
| `pe-streferralindev<suffix>-queue` | Storage | `queue` | `privatelink.queue.core.windows.net` |
| `pe-sql-referralintake-dev-centra-<suffix>` | SQL server | `sqlServer` | `privatelink.database.windows.net` |
| `pe-kv-referralintake-<suffix>` | Vault | `vault` | `privatelink.vaultcore.azure.net` |
| `pe-crreferralintakedev<suffix>` | ACR | `registry` | `privatelink.azurecr.io` |
| `pe-doc-referralintake-dev-<suffix>` | Document Intelligence | `account` | `privatelink.cognitiveservices.azure.com` |
| `pe-ai-referralintake-dev-<suffix>` | Content Understanding | `account` | `privatelink.cognitiveservices.azure.com` |
| `pe-func-referralintake-dev` | Function, after section 12 creates it | `sites` | `privatelink.azurewebsites.net` |

Check each connection is **Approved**, its NIC has a private address in `10.21.3.0/24`, and its DNS zone group points at the intended zone. Inspect the A records, including ACR data endpoint records and Function/SCM records created by the DNS integration. Do not manually guess endpoint IPs. Check both hub/spoke zone links or approved central DNS forwarding.

The private endpoint resource, its NIC, and the DNS zone group are distinct resources even if the wizard creates them together. Function outbound VNet integration and its inbound private endpoint are also separate settings. ACA uses the internal environment/static IP in section 11; this design does **not** add a ninth, ACA private endpoint.

## 8. Administrator runtime IAM grants

For each target below open **Access control (IAM) > Role assignments**. Reuse an existing equivalent grant; otherwise **Add role assignment > role > Members > Managed identity**, choose the exact principal, and **Review + assign**. Use principal/object IDs to distinguish duplicate names.

| Target scope | Principal | Role | Assignments |
|---|---|---|---|
| Workload storage account | Function identity and ACA identity | Storage Blob Data Contributor | 2 |
| Workload storage account | Function identity and ACA identity | Storage Queue Data Contributor | 2 |
| Workload storage account | Event Grid system topic's system identity | Storage Queue Data Message Sender | 1 |
| Document Intelligence account | Function identity and ACA identity | Cognitive Services User | 2 |
| Content Understanding account | Function identity and ACA identity | Cognitive Services User | 2 |
| ACR | Function identity and ACA identity | AcrPull | 2 |
| Vault, if jumpbox is used | Configured jumpbox secret-reader group/user | Key Vault Secrets User | 1 optional |

That is **11 required assignments plus one conditional assignment**. Do not assign these roles subscription-wide or replace them with Owner. If the Event Grid identity is not listed as a selectable managed identity, select the exact service principal through the member picker and confirm its principal ID.

The human using storage portal data blades also needs **Storage Blob Data Contributor** / **Storage Queue Data Contributor** on the storage account for creation and testing; grant these separately to the approved setup operator, not every Contributor. Portal IAM access does not bypass the data network firewall. The vault writer permission from section 5 is likewise separate.

Allow IAM propagation before testing image pulls and event delivery. If a UI still attempts an automatic role grant, have the access administrator complete/verify it rather than broadening the deployer's role.

### Storage trusted-service configuration

In **storage > Networking > resource settings / exceptions**, configure the template's **Allow Azure services on the trusted services list** exception and a **Resource instance** rule for the specific `Microsoft.EventGrid/systemTopics` resource `evgt-referralintake-dev` in this tenant. Do not choose all resources in the subscription. Preserve public access **Disabled**, default network action **Deny**, and shared keys **Disabled**.

The template relies on trusted-service/resource-instance access for Event Grid's queue delivery; Event Grid does not push through your private endpoint. If the disabled-public-access UI hides these exception controls, record a parity gap and validate with the storage administrator. Do not switch public access on as an undocumented workaround. The delivery test in section 16 is required to establish that the combination works in this environment.

Sources: [portal resource-instance rules](https://learn.microsoft.com/azure/storage/common/storage-network-security-resource-instances), [Event Grid identity-based delivery](https://learn.microsoft.com/azure/event-grid/managed-service-identity).

## 9. Initialize SQL through the portal

Use the **Azure portal opened inside the jumpbox browser**, signed in as a member of the configured SQL administrator group. An existing privately connected browser is also suitable.

1. Open **SQL database > sqldb-referralintake > Query editor**.
2. Select **Continue as** the authorized Entra administrator. Do not add a public firewall exception or enable SQL passwords.
3. Run this in the **application database**, replacing the identity names if the worksheet uses different ones:

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

This is the SQL in [`bootstrap-sql.sql`](../scripts/bootstrap-sql.sql) with SQLCMD variables replaced; Query Editor does not need SQLCMD directives. On an existing environment, inspect **Security > Users** and role membership first and execute only missing grants. Confirm each existing database principal represents the intended managed identity, not merely a matching display name.

`CREATE USER ... FROM EXTERNAL PROVIDER` requires directory resolution. If it fails, have the SQL/Entra administrators resolve the required directory permissions or ambiguous identity; subscription Owner alone does not fix that. Do not grant directory-wide permissions blindly.

Microsoft Learn explicitly supports [Query Editor with a private-link connection from within the private network](https://learn.microsoft.com/azure/azure-sql/database/query-editor#connection-considerations). Current documentation states Query Editor uses outbound HTTPS port 443. If the customer's browser/network/portal experience cannot connect privately, mark SQL initialization **blocked** and involve the network/SQL owner; this strict UI guide does not substitute SSMS or a command.

The real API initializes tables and additive columns on startup through [`database.py`](../api/referral/database.py). Database users/roles must exist first; a green database resource does not establish application readiness.

## 10. Consumption Logic App

Search **Logic apps > Add**, select **Consumption**, target group, East US 2, name `logic-referralintake-notification-dev`. Enable **Identity > System assigned**, matching the template. Do not choose Standard hosting, which has different resources and configuration.

Open **Logic app designer** and create:

1. **When an HTTP request is received**, method **POST**, with this request body schema:

```json
{
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
```

2. Add **Control > Switch**, action name `Route_event`, with expression `triggerBody()?['event']` (enter expressions through the expression editor, without wrapping them in literal text).
3. Add case `referral.failed`, named `Intake_failed`, containing **Data Operations > Compose** named `Raise_intake_failure`, with object input:

```json
{
  "severity": "error",
  "summary": "Referral intake failed for @{triggerBody()?['filename']}",
  "reason": "@triggerBody()?['reason']",
  "detail": "The document is in the failed container and did not reach the review queue. Add a Teams, Outlook, or ticketing action here to page whoever owns intake.",
  "payload": "@triggerBody()"
}
```

4. In the default branch add **Compose**, named `Record_review_decision`, with object input:

```json
{
  "severity": "information",
  "summary": "@{triggerBody()?['event']} for @{triggerBody()?['filename']}",
  "reviewedBy": "@triggerBody()?['reviewedBy']",
  "detail": "A reviewer reached a decision. Add a downstream action here to hand the referral to the system of record.",
  "payload": "@triggerBody()"
}
```

5. After the Switch succeeds, add **Response**, named `Acknowledge`, status **202**, object body:

```json
{ "accepted": true, "event": "@triggerBody()?['event']" }
```

Use the supported designer expression/object input or its **Code view** to retain expressions as expressions, not quoted JSON strings. Compare the saved workflow with [`integration.bicep`](../infra/modules/integration.bicep): the trigger is `manual`, the Switch runs first, the Response follows its successful completion, and the workflow is **Enabled**.

Save and copy the Request trigger's generated **HTTP URL** into approved secret handling. This signed URL becomes `LOGIC_APP_URL` in the API and Function; do not post it in tickets or logs. The template's Consumption workflow uses an HTTP callback and is not placed behind a private endpoint. It records Compose outputs; it does **not** send real Teams/email/ticket notifications until separately configured.

## 11. Container Apps environment, private ingress, and web/API

Source: [`compute.bicep`](../infra/modules/compute.bicep). Follow Microsoft's [portal VNet procedure](https://learn.microsoft.com/azure/container-apps/vnet-custom?pivots=azure-portal) using this guide's values, not the sample defaults.

1. Search **Container Apps > Create**. Name `ca-referralintake-web-dev`, East US 2, deployment source **Container image**.
2. Create environment `cae-referralintake-dev`; zone redundancy **Disabled**; monitoring **Azure Log Analytics**, selecting `log-referralintake-dev`.
3. Under environment **Networking**, use your own VNet, select the spoke and `snet-aca`, and set the environment **Virtual IP: Internal**. Check the workload-profile/subnet compatibility noted in section 3. Do not select an external environment plus a separate Private Link endpoint as an equivalent.
4. If the wizard requires an initial container before identity attachment, use its public quickstart image only to establish the resource, mark it **placeholder only**, and complete the following steps before any readiness declaration. Do not use placeholders on an already running environment.
5. Open **Container App > Identity > User assigned > Add** and attach `id-referralintake-aca-dev`.

### Environment DNS

On the environment **Overview / Properties**, record **default domain** and **static IP**. Create a private DNS zone named **exactly that default domain**, then an **A record set** named `*`, TTL **300 seconds**, pointing to the environment static IP. Add hub and spoke VNet links, autoregistration disabled. These are additional to the seven service zones.

### Configure the real two-container revision

Open the app's **Containers / Revision management > Edit and deploy / Create new revision**. Use the container list to configure `web` and add `api` in the same revision; both share localhost. If the current UI does not expose adding a second regular container, record a **portal parity blocker**. Do not split them into two apps without an application redesign.

| Setting | `web` | `api` |
|---|---|---|
| Image | `<ACR_LOGIN_SERVER>/referral-web:<tag>` | `<ACR_LOGIN_SERVER>/referral-api:<tag>` |
| Image authentication | Managed identity `id-referralintake-aca-dev` | Same |
| Resources | 0.5 vCPU, 1 GiB | 0.5 vCPU, 1 GiB |
| Command/arguments | Leave image defaults | Leave image defaults |
| Environment variables | `API_BASE_URL=http://127.0.0.1:7071` | Section 14 |
| Explicit probe | Liveness HTTP `GET /`, port 8080; initial delay 10 seconds, period 30 seconds | No custom probe declared in template |

Do not enable ACR admin credentials if the image picker cannot list tags; enter the approved image/tag manually. See [portal managed-identity image pull](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull).

Under **Ingress**, enable HTTP ingress, select **accept traffic from anywhere** / external app ingress, target port **8080**, transport **Auto**, insecure connections **Disabled**. Despite the label, the environment's **Internal** VIP keeps this ingress private. Environment-only app ingress would prevent jumpbox access. Do not expose port 7071 separately.

Under **Scale**, set minimum **1**, maximum **3**, HTTP scale rule `http`, concurrent requests **50**. Keep **Single revision** mode. Use the Authentication settings in section 13 before the app is considered ready.

Reference: [multi-container architecture](https://learn.microsoft.com/azure/container-apps/containers), [revision lifecycle](https://learn.microsoft.com/azure/container-apps/revisions). These documents establish service capabilities, not a guarantee that every advanced property has a control in every portal version.

## 12. Function App and private networking

Create a **Function App** named `func-referralintake-dev`, **Linux**, **container** deployment, East US 2. Choose **Elastic Premium EP1** plan `asp-referralintake-func-dev`, minimum capacity **1**, maximum elastic worker count **3**. Do not choose Flex Consumption, Windows, a code/zip deployment, or Functions hosted inside Container Apps; this reference uses `Microsoft.Web/sites`.

If the wizard requires a bootstrap storage connection or account-key configuration, do not enable shared-key access on the workload storage account to get past it. Record the creation-time UI limitation; identity-based settings below must replace any generated key-based settings before startup.

1. Under **Identity > User assigned**, attach `id-referralintake-func-dev`.
2. Under **Deployment Center**, source **Container registry**, select ACR/repository `referral-func` and the approved immutable tag, authentication **Managed identity**, select the Function identity. If the UI does not expose selecting that user-assigned identity, record a blocker rather than using registry username/password.
3. Under **Networking > VNet integration**, add outbound integration with spoke subnet `snet-functions`. Enable routing of all outbound application traffic through the VNet. Check container image-pull routing is also VNet-enabled if using private ACR; a private endpoint alone does not route outbound image pulls.
4. Create the Function's `sites` private endpoint from section 7, then verify **public network access Disabled**. Keep HTTPS-only enabled, minimum TLS **1.2**, FTPS **Disabled**, Always On enabled where the portal exposes it.
5. Enter section 14's Function settings in **Settings > Environment variables / Configuration > Application settings**, save, and restart when SQL grants and images are ready.

The template's relevant site properties are `acrUseManagedIdentityCreds=true`, `acrUserManagedIdentityID=<FUNC_CLIENT_ID>`, `vnetRouteAllEnabled=true`, and `keyVaultReferenceIdentity=<FUNC_IDENTITY_RESOURCE_ID>`. They are site properties, **not ordinary app-setting names**. Set them through their actual UI controls if available; otherwise record the gap. This app does not currently use a Key Vault reference for its database connection. Do not claim that adding similarly named environment variables configures these properties.

Sources: [Functions custom containers and portal image updates](https://learn.microsoft.com/azure/azure-functions/functions-how-to-custom-container?pivots=azure-functions), [container registry authentication and networking](https://learn.microsoft.com/azure/app-service/configure-custom-container).

## 13. Entra authentication and callbacks

Once hostnames exist, the application administrator opens **Entra ID > App registrations > selected app > Authentication** and adds **Web** redirects:

- `https://<web-fqdn>/.auth/login/aad/callback`
- `https://<function-hostname>/.auth/login/aad/callback`

Preserve any existing valid redirects. Neither address is a wildcard or a localhost callback.

On **Container App > Authentication > Add identity provider**, choose **Microsoft**, use the **existing** registration in the worksheet:

| Setting | Value |
|---|---|
| Authentication | Enabled |
| Tenant / client ID | Worksheet tenant and `ENTRA_CLIENT_ID` |
| Issuer | `https://sts.windows.net/<TENANT_ID>/v2.0` as declared in the template |
| Allowed token audience | `api://<ENTRA_CLIENT_ID>` |
| Unauthenticated action | Redirect to Microsoft sign-in |
| Token store | Disabled |
| Additional principal restriction | None declared in the template; tenant/customer policies still apply |

On **Function App > Authentication**, use the same existing registration/issuer/audience, **Require authentication**, unauthenticated action **HTTP 401**, token store disabled.

The [Container Apps existing-registration instructions](https://learn.microsoft.com/azure/container-apps/authentication-entra) describe an optional client secret. This template does not configure one. Avoid automatic-registration mode, which can create a secret and a different app. If a UI insists on a client secret or cannot represent the template issuer/settings, mark the exact parity gap and have the identity owner resolve it; do not change the authentication design silently.

## 14. Complete application settings

Replace every angle-bracket placeholder with a recorded value. Use the ACA identity for the API and the Function identity for the Function. Keep the web container's single variable separate from the API.

### Shared by the API container and Function App

| Name | Value / source |
|---|---|
| `DATABASE_URL` | `mssql+pyodbc://@<SQL_SERVER_FQDN>/sqldb-referralintake?driver=ODBC+Driver+18+for+SQL+Server&authentication=ActiveDirectoryMsi&UID=<IDENTITY_CLIENT_ID>` |
| `AZURE_CLIENT_ID` | `<ACA_CLIENT_ID>` for API; `<FUNC_CLIENT_ID>` for Function |
| `STORAGE_ACCOUNT_URL` | `https://<storage-name>.blob.core.windows.net` |
| `QUEUE_ACCOUNT_URL` | `https://<storage-name>.queue.core.windows.net` |
| `QUEUE_NAME` | `referral-jobs` |
| `INCOMING_CONTAINER` | `incoming` |
| `PROCESSING_CONTAINER` | `processing` |
| `FAILED_CONTAINER` | `failed` |
| `ARCHIVE_CONTAINER` | `archive` |
| `LOGIC_APP_URL` | Signed Request-trigger URL from section 10; treat as secret |
| `DOCUMENT_INTELLIGENCE_ENDPOINT` | Recorded Document Intelligence custom-subdomain endpoint |
| `CONTENT_UNDERSTANDING_ENDPOINT` | Recorded Content Understanding custom-subdomain endpoint |
| `CONTENT_UNDERSTANDING_ANALYZER` | `referralIntake` |
| `CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT` | `gpt-5.2` |
| `CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` |
| `LOCAL_MOCK_IDENTITY` | `false` |
| `ALLOW_LOCAL_MOCK_EXTRACTION` | `false` |

In Container Apps, store the callback URL under **Secrets**, then set `LOGIC_APP_URL` as a secret reference on the API container. This is an explicit improvement over the template's direct environment value, without changing application behavior. In Function settings, treat it as sensitive configuration and restrict configuration access. Do not include the callback in screenshots or paste it into a public worksheet.

### Function-only settings

| Name | Value / source |
|---|---|
| `FUNCTIONS_WORKER_RUNTIME` | `python` |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` |
| `DOCKER_REGISTRY_SERVER_URL` | `https://<ACR_LOGIN_SERVER>` |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE` | `false` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recorded Application Insights connection string |
| `AzureWebJobsStorage__accountName` | Workload storage account name |
| `AzureWebJobsStorage__credential` | `managedidentity` |
| `AzureWebJobsStorage__clientId` | `<FUNC_CLIENT_ID>` |

Do not leave a generated connection-string `AzureWebJobsStorage` setting alongside these identity-based values, or generated registry username/password settings that defeat managed-identity authentication. Review before removal: do not delete unrelated existing settings. The Dockerfile supplies the Function runtime/dependencies; setting Python in the portal does not install this application into a base image.

## 15. Final event wiring, diagnostics, and Defender

### Event subscription

After queues and runtime grants exist, open **Event Grid System Topics > evgt-referralintake-dev > Event subscriptions > Add**:

| Setting | Value |
|---|---|
| Name | `referral-incoming` |
| Event schema | Event Grid Schema |
| Event types | Only **Blob Created** (`Microsoft.Storage.BlobCreated`) |
| Endpoint type | **Storage Queue**, not Web Hook or Azure Function |
| Endpoint | Workload storage account, queue `referral-jobs` |
| Delivery managed identity | **System assigned**, the system topic's identity |
| Subject begins with | `/blobServices/default/containers/incoming/blobs/` |
| Subject ends with | Empty |
| Max delivery attempts | 10 |
| Event time to live | 1440 minutes |
| Queue message TTL | 604800 seconds / 7 days |
| Dead-letter destination | Not configured in the template |

Use **Filters** for the subject filter and **Additional features** for retry/identity settings. If the queue TTL control is not exposed, record that exact property gap rather than assuming the default matches. Shared-key queue delivery is not equivalent. On an authorization error, verify the sender grant and propagation; do not repeatedly recreate the topic/identity.

### Diagnostics and alert

Open **Function > Diagnostic settings > Add**: name `diag-func-referralintake-dev`, enable **FunctionAppLogs** and **AllMetrics**, send to the existing workspace. On **Logic App > Diagnostic settings**, name `diag-logic-referralintake-notification-dev`, select **allLogs** and **AllMetrics**, same workspace. Container Apps environment logging was configured in section 11. Event Grid metrics are viewable in its Metrics blade; the templates do not configure a separate Event Grid diagnostic export.

In **Log Analytics workspace > Logs**, use this query for the alert:

```kusto
union isfuzzy=true
    (FunctionAppLogs | where Level == "Error" | project TimeGenerated),
    (ContainerAppConsoleLogs_CL | where Log_s has "failed during processing" | project TimeGenerated)
```

Create an **alert rule** scoped to the workspace, name `alert-referralintake-failed-jobs-dev`, display name **Referral processing failures**, severity **2**, enabled, evaluation every **5 minutes**, lookback **15 minutes**, aggregation **Count**, threshold **Greater than 0**, one violation out of one evaluation period, automatic resolution enabled. The template has no action group; it creates an alert but does not page anyone. Adding notification recipients is a separate customer choice.

### Subscription Defender settings: administrator only

In **Microsoft Defender for Cloud > Environment settings > target subscription > Defender plans**, review existing settings and costs with the subscription security owner. The reference requests Standard pricing for **AppServices, Containers, KeyVaults, SqlServers, StorageAccounts, VirtualMachines**. Portal product names can group these differently; verify coverage rather than enabling every displayed plan.

Apply only approved changes and record them. Do not reset customer-selected subplans or assume the template enables every malware-scanning feature. Defender is not required merely to create the app resources, but omitting approved reference coverage is an explicit deviation. See [Defender setup and billing](https://learn.microsoft.com/azure/defender-for-cloud/connect-azure-subscription) and the storage system-topic conflict in section 5.

## 16. Verify a working deployment

Use the private browser session. Keep an evidence record without credentials or document contents.

| Check | Portal/browser evidence |
|---|---|
| Network | Both peerings Connected; all eight endpoint connections Approved; service zone links/records and ACA wildcard record present |
| Images | All three approved image tags in ACR; Function points at `referral-func`, not a base image; ACA revision contains both `web` and `api` |
| Runtime | Latest ACA revision provisioned/running with healthy containers; Function host starts and indexes the queue trigger |
| SQL | Both managed-identity users and required roles exist; application tables appear after API startup |
| AI initialization | API logs show Content Understanding defaults/analyzer setup succeeded; absence of startup failure is insufficient because analyzer provisioning runs in a background thread |
| Authentication | Web URL from jumpbox redirects to the approved tenant and loads the operator app after sign-in; API is not anonymously exposed through ingress |
| Event source | Event subscription filter selects only incoming blobs; queue delivery identity is the topic's system identity |
| End-to-end | A new synthetic sample reaches human review, then approval/return produces the expected archive/failed state and Logic App run |

For the event test, open **storage > Containers > incoming > Upload** from the private browser with the setup operator's blob data role. Upload one previously unused document from [`samples`](../samples/README.md). This tests the pipeline independently of the web upload simulator. The data-processing guardrails reject duplicate document hashes, so use a fresh sample for a repeated test.

In **system topic > Metrics**, inspect published, matched and delivered events; in **Storage > Queues**, inspect processing/poison queue activity without modifying or deleting messages. In **Container App > Logs** and **workspace > Logs**, inspect startup and processing. The private Function's live log stream may be unreachable; use the configured `FunctionAppLogs` instead.

Open the application review queue in the jumpbox browser, inspect the two-engine comparison, and approve or return the sample. Then inspect **Logic App > Runs history** and the appropriate storage container. A failure moves to `failed`; a successful approval archives the document. The Logic App's Compose branch records the handoff but does not create a real downstream business integration.

### Troubleshooting without weakening security

| Symptom | Check first |
|---|---|
| Provider registration denied | Correct subscription; registration is a subscription-admin prerequisite, not a resource-group Contributor task |
| IAM add denied | Access administrator must assign the specific role at the resource scope |
| Portal storage/vault blade denied | Browser's private DNS/network path and the human's data-plane role, not just Contributor |
| Image pull unauthorized | Correct identity attachment/client ID, AcrPull on RBAC-mode registry, ARM-audience acceptance, propagation |
| Image pull times out | ACR private DNS including data endpoint records, private connectivity and Function image-pull routing |
| App URL fails only from jumpbox | Hub link/forwarding for ACA DNS, environment Internal plus app-level external ingress, both peerings |
| API revision fails at startup | SQL private DNS, Entra user/roles, identity client ID in database URL |
| Models/analyzer fail | Exact account, Global Standard deployments, model availability/quota, AI role grants and API provisioning logs |
| Incoming blob remains unprocessed | Real Function image/indexed trigger; topic delivery metrics, identity queue grant, storage exception, correct event filter |
| No business notification arrives | Reference Logic App only records Compose output; an approved connector action must be configured separately |
| Wizard does not expose required setting | Record the property and resource as a portal parity gap; do not substitute a public endpoint, account key, Cloud Shell, or custom template |

## Source map and remaining portal-only gaps

| Configuration | Repository source |
|---|---|
| Overall graph, parameters and regions | [`main.bicep`](../infra/main.bicep), [`main.bicepparam`](../infra/main.bicepparam) |
| Network and NSG rules | [`network.bicep`](../infra/modules/network.bicep) |
| Vault and identities | [`identity-security.bicep`](../infra/modules/identity-security.bicep) |
| Storage, SQL and system topic | [`data.bicep`](../infra/modules/data.bicep) |
| AI accounts and deployments | [`ai.bicep`](../infra/modules/ai.bicep) |
| Registry | [`registry.bicep`](../infra/modules/registry.bicep) |
| Containers, Function, ingress, auth and settings | [`compute.bicep`](../infra/modules/compute.bicep) |
| Event subscription | [`eventing.bicep`](../infra/modules/eventing.bicep) |
| Workflow | [`integration.bicep`](../infra/modules/integration.bicep) |
| Monitoring | [`observability.bicep`](../infra/modules/observability.bicep) |
| Bastion and jumpbox | [`bastion.bicep`](../infra/modules/bastion.bicep), [`jumpbox.bicep`](../infra/modules/jumpbox.bicep) |
| Subscription security | [`defender.bicep`](../infra/modules/defender.bicep) |

**Known external prerequisite:** image building/publishing is not provided by this portal-only runbook. **UI-dependent parity checks:** advanced authentication/site properties, storage trusted-service exceptions while public access is disabled, ACR ARM-audience acceptance, multi-container controls, and queue message TTL must be verified in the customer's portal experience. Foundry model management can require its own portal/project. Any unresolved item belongs in the handoff as **blocked / not configured**, not "deployment complete."

Use the [operations guide](operations.md) for additional diagnostics, recognizing that its command-based procedures are outside this runbook's UI-only boundary.
