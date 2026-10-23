# Deployment roles and least-privilege access

This guide maps **what this repository deploys** to **who needs which permissions, at which scope**. It covers infrastructure deployment, image publishing, runtime identities, and workshop participants separately. The role recommendations use Microsoft built-in roles, not custom roles.

**Recommended approach:** let a platform administrator prepare the subscription and resource group, then delegate the [resource-group deployments](#delegated-infrastructure-deployer) and [image-only publishing](#image-publisher) using service-specific roles. Do not give every participant or routine publisher subscription Contributor.

Start with the [deployment inventory](#deployment-inventory), [role consolidation table](#when-one-role-can-cover-several-services), and [account bundles](#account-bundles). For access after deployment, see [runtime identities](#runtime-identities) and [participants and operators](#participants-and-operators).

## How to read the recommendations

The narrowest suitable **built-in** role can still grant more than the exact operations this sample needs. Fewer role assignments are not necessarily less privilege. Permissions are additive across roles and inherited scopes; a narrow assignment does not cancel a broad inherited assignment. Follow [Microsoft Learn's RBAC best practices][rbac-practices]: narrow scopes, group-based human access, time-bound elevation, and constrained access delegation.

| Permission boundary | What it controls | What it does not replace |
|---|---|---|
| Azure control-plane RBAC | Create/configure Azure resources and deployment records | Entra application ownership, SQL database grants, or data access |
| Azure data-plane RBAC | Read/write blobs, queue messages, secrets, AI operations, or images, depending on the service | Permission to deploy the service itself |
| Microsoft Entra / Microsoft Graph | App registrations, service principals, directory operations and consent | Azure resource permissions |
| Azure SQL database permissions | Connect, create users/schema, read/write application tables | SQL server management through ARM |
| Network and application/OS access | Reach private endpoints; authenticate to the app or jumpbox | Any of the permissions above |

Owner is an Azure resource/access administration role, not a universal account across these boundaries. Contributor manages Azure resources but **cannot create Azure RBAC role assignments**. Neither automatically gives Graph permissions, SQL database access, or secret/blob data access. Some control-plane roles can nevertheless change authentication settings or workload code and thereby obtain effective data access; treat those roles as privileged.

### Root deployment versus delegated deployment

[`infra/main.bicep`](../infra/main.bicep) is **subscription-scoped**. Every run declares the resource group and deploys six subscription-level Defender plans, as well as the resource-group workload. Precreating the group does not remove those subscription writes from the root template.

There is no purpose-built **Resource Group Contributor** role in the [published Azure built-in role catalog][roles]. Do not confuse Contributor *assigned at resource-group scope* with a separate, narrower role. The service-role bundle below does not grant `Microsoft.Resources/subscriptions/resourceGroups/write` or general provider registration. For the unchanged root, a platform bootstrap identity with subscription Contributor plus scoped role-assignment authority is the broad fallback, **not the least-privilege recommendation**. Owner is not necessary. An exact-action subscription bootstrap role would require a custom role, outside this guide's scope.

To avoid subscription Contributor on the workload deployer, use the existing [`infra/entrypoints`](../infra/entrypoints) with a platform-created group and platform-managed provider registration/Defender configuration. This is a different deployment path, not a claim that the unchanged root can run with resource-group permissions alone.

## Deployment inventory

**Scope notation:** **RG** means the workload resource group, normally `rg-referralintake`; **resource** means a particular existing resource and its children. Creation permissions generally need RG scope because the resource does not exist yet. For updates, use resource scope when the operation and its linked-resource permissions allow it.

The tables name service-management roles; **add the shared requirements below** for a complete deployment. A role in a service row is not sufficient for every resource in that Bicep module.

### Shared deployment requirements

| Capability | Suitable built-in role and scope | Repository-specific dependency / limit |
|---|---|---|
| ARM deployment and default what-if validation | A role containing `Microsoft.Resources/deployments/*` at the deployment scope, plus write permission on each declared resource | Most service contributor roles include deployments; **Container Apps Contributor does not**. In the combined compute bundle, ManagedEnvironments Contributor / Website Contributor supplies it at RG scope. A service role at resource scope does not grant RG deployment rights. See [Bicep permissions][what-if]. |
| Create runtime Azure role assignments | **Role Based Access Control Administrator** at RG, preferably constrained to the [runtime roles and principals](#runtime-identities) | Requires `Microsoft.Authorization/roleAssignments/write`. Service contributors and Managed Identity Operator do not grant it. Key Vault Data Access Administrator can be a narrower alternative for the Key Vault grants alone, not for Storage/AI/ACR grants. |
| Attach the two user-assigned identities to ACA and Functions | **Managed Identity Operator** on those identity resources | Supplies `Microsoft.ManagedIdentity/userAssignedIdentities/*/assign/action`, in addition to permission to write the app. **Managed Identity Contributor does not include assign**. |
| Create private endpoints, DNS zone groups, VNet links, peerings and subnet integrations | **Network Contributor** at RG (or the relevant network scopes for separately delegated existing resources) | Includes `Microsoft.Network/*`, subnet join and private DNS operations. Also need the target service's private-endpoint approval/write permissions; use its management role from the inventory. DNS access alone is not endpoint or target-service approval authority. |
| Read Log Analytics shared keys used by the ACA environment | **Monitoring Contributor** or **Log Analytics Contributor** on the workspace; RG scope when creating it | `observability.bicep` calls `workspace.listKeys()`; the relevant permission is `Microsoft.OperationalInsights/workspaces/sharedKeys/action`. Reader alone is not a substitute. |
| Obtain the notification trigger callback URL | **Logic App Contributor** on the workflow; RG scope when creating it | The root calls `Microsoft.Logic/workflows/triggers/listCallbackUrl/action`. The URL contains a SAS credential; do not expose it in logs or outputs. RG entry points receive the URL as a secure parameter instead. |
| Write diagnostic settings | **Monitoring Contributor** at the resources receiving settings, plus workspace access | Needed for Functions and Logic App diagnostics. Logic App Contributor already includes diagnostic settings for its scope; Website Contributor does not generally grant `Microsoft.Insights/diagnosticSettings/*`. |
| Read referenced resources and discover outputs | Read access on each referenced resource; often already included in the corresponding service roles | Cross-RG networking, identities or workspaces need assignments at those other scopes too. The unchanged workflow's `az acr list -g` needs registry read/list at RG, not just access to a named registry. |

Avoid granting an unconstrained RBAC administrator merely to make Bicep succeed. Use [role-assignment delegation conditions][delegation] to restrict assignable role IDs and recipients. A platform administrator can create the RG and establish this delegation before the deployer runs. Newly created workload/system-topic principal IDs are not known in advance; stage their creation before pinning recipient IDs, or explicitly review a less restrictive condition for bootstrap. Preassigning roles is not enough to remove the deployer's authorization requirement while the unchanged modules still declare those role-assignment writes.

### Subscription and bootstrap resources

| What is deployed / configured | Source | Suitable permission / role | Scope and boundary |
|---|---|---|---|
| Resource group and root deployment record | [`main.bicep`](../infra/main.bicep) | Platform-owned creation; **Contributor** is the broad built-in fallback, as explained above | Subscription. RG-scoped service roles cannot create the group or authorize the root deployment. |
| Resource-provider registration | [Deployment prerequisites](deployment.md#prerequisites) | Platform identity with each provider's `/register/action`; subscription **Contributor** includes these | One-time subscription preparation, not a reason to retain Contributor for image publishing. Include `Microsoft.EventGrid` and `Microsoft.ManagedIdentity` as well as the other namespaces used by the templates. |
| Defender Standard plans: `AppServices`, `Containers`, `KeyVaults`, `SqlServers`, `StorageAccounts`, `VirtualMachines` | [`defender.bicep`](../infra/modules/defender.bicep) | **[Security Admin][security-roles]** | Subscription. Includes `Microsoft.Security/*` and deployment operations, but is broader than pricing changes and includes policy management. These changes can affect other resources and billing. Contributor already covers them if using the broad root fallback; do not add Security Admin redundantly. |

### Workload resources

All rows use RG scope for creation unless specified otherwise. The shared networking, identity attachment, diagnostics, deployment and RBAC requirements apply in addition to the roles shown.

| Service / everything deployed in this area | Source | Narrowest suitable built-in management role(s) for these operations | Additional requirements / important distinction |
|---|---|---|---|
| Hub and spoke VNets; five subnets including `AzureBastionSubnet`; three NSGs; two peerings; Bastion Standard public IP | [`network.bicep`](../infra/modules/network.bicep) | **[Network Contributor][network-roles]** | Must cover both VNets for peering. Does not grant VM management or role assignment. |
| Seven private DNS zones (Blob, Queue, SQL, Key Vault, ACR, Cognitive Services, App Service) and spoke VNet links | [`network.bicep`](../infra/modules/network.bicep) | **[Private DNS Zone Contributor][network-roles]** for DNS-only work, or the Network Contributor already needed above | VNet linking needs join access on the linked VNet. Do not add Private DNS Zone Contributor where Network Contributor already covers the same scopes. |
| Private endpoints and DNS zone groups for Blob, Queue, SQL, Key Vault, ACR, both AI accounts and Functions | [`data`](../infra/modules/data.bicep), [`identity-security`](../infra/modules/identity-security.bicep), [`registry`](../infra/modules/registry.bicep), [`ai`](../infra/modules/ai.bicep), [`compute`](../infra/modules/compute.bicep) modules | **Network Contributor** plus each target service's management role | Endpoint-side networking permission alone does not approve a connection on the target service. DNS records also require zone access. |
| Two user-assigned managed identities (`id-...-func-...`, `id-...-aca-...`) | [`identity-security.bicep`](../infra/modules/identity-security.bicep) | **[Managed Identity Contributor][identity-roles]** | Add **Managed Identity Operator** on the identities to attach them to apps. Granting access *to* identities is the separate RBAC administration requirement. |
| RBAC-enabled Key Vault; conditional `jumpbox-admin-password` ARM secret | [`identity-security.bicep`](../infra/modules/identity-security.bicep) | **[Key Vault Contributor][security-roles]** | The secret is declared as [`Microsoft.KeyVault/vaults/secrets`][arm-secret], an ARM write covered by `Microsoft.KeyVault/*`. This does **not** grant data-plane secret retrieval or `az keyvault secret set`. Conditional Secrets User assignment also needs RBAC authority. |
| Storage account; Blob service and `incoming`, `processing`, `failed`, `archive` containers; Queue service and `referral-jobs`, `referral-jobs-poison` queues | [`data.bicep`](../infra/modules/data.bicep) | **[Storage Account Contributor][storage-roles]** | Covers ARM container/queue provisioning and target private-endpoint configuration, not OAuth blob/message operations. It can manage authentication settings/list keys; it is not a harmless data-reader role. |
| Event Grid system topic with system-assigned identity; `referral-incoming` event subscription delivering BlobCreated events to the queue | [`data.bicep`](../infra/modules/data.bicep), [`eventing.bicep`](../infra/modules/eventing.bicep) | **[EventGrid Contributor][integration-roles]** | The queue-sender role assigned to the topic is separate. Source/destination read access comes from Storage management access in this bundle. EventGrid EventSubscription Contributor alone does not cover system-topic creation or the explicit `systemTopics/eventSubscriptions/*` action family in these templates. |
| Azure SQL logical server, configured Entra administrator group and Entra-only authentication; S0 database | [`data.bicep`](../infra/modules/data.bicep) | **[SQL Server Contributor][database-roles] + [SQL Security Manager][database-roles]** | Server Contributor already covers database management, so SQL DB Contributor is redundant here. It explicitly excludes Entra-only authentication changes; Security Manager supplies those. Neither supplies SQL table access. See [Entra-only authentication permissions][sql-entra-only]. |
| Document Intelligence (`FormRecognizer`) account; Content Understanding (`AIServices`) account; `gpt-5.2` completion and `text-embedding-3-large` embedding deployments | [`ai.bicep`](../infra/modules/ai.bicep) | **[Cognitive Services Contributor][ai-roles]** | One role covers both accounts and ARM model deployments. Runtime token operations use a different role. Custom analyzer/default configuration happens in the API at runtime, not in Bicep. |
| Premium container registry, network/authentication settings and retention policy | [`registry.bicep`](../infra/modules/registry.bicep) | **[Container Registry Contributor and Data Access Configuration Administrator][container-roles]** | Management only: not a substitute for Tasks Contributor, direct push/pull, or role-assignment authority. Includes powerful authentication configuration access despite the long service-specific name. |
| Internal Container Apps managed environment; one Container App with `web` and `api` containers; ingress, scaling, image/identity configuration and Easy Auth | [`compute.bicep`](../infra/modules/compute.bicep) | **[Container Apps ManagedEnvironments Contributor][container-roles] + [Container Apps Contributor][container-roles]** | App Contributor can read/join an environment, not create it. Add identity attachment, subnet permissions and workspace key access. The two containers are not two separately deployed Container Apps. |
| Optional environment-domain private DNS zone, wildcard A record, hub and spoke links on the second deployment | [`compute.bicep`](../infra/modules/compute.bicep) | **Private DNS Zone Contributor**, or existing **Network Contributor** | Only created when `containerAppsDefaultDomain` is supplied. Cover both linked VNets. |
| Functions EP1 Premium App Service plan; Linux container Function App; settings, VNet integration, Easy Auth and diagnostic settings | [`compute.bicep`](../infra/modules/compute.bicep) | **[Web Plan Contributor][web-roles] + [Website Contributor][web-roles]** | Website Contributor can join/read a plan but not create it. Add network, identity attachment and monitoring permissions. Image-only rollout does not require plan creation rights. |
| Log Analytics workspace; Application Insights component; `Referral processing failures` scheduled-query alert | [`observability.bicep`](../infra/modules/observability.bicep) | **[Monitoring Contributor][monitor-roles]** | Covers workspace creation/write, shared keys, Insights components, scheduled-query rules and diagnostics. See consolidation tradeoffs below; Log Analytics Contributor alone does not write scheduled-query rules. |
| Consumption notification Logic App, request trigger, routing/Compose actions, system-assigned identity and diagnostic settings | [`integration.bicep`](../infra/modules/integration.bicep) | **[Logic App Contributor][integration-roles]** | Covers callback URL retrieval and diagnostics, not authorization to Teams/Outlook/other connectors a participant might add. The template creates no API connection resources. |
| Basic Azure Bastion host | [`bastion.bicep`](../infra/modules/bastion.bicep) | **Network Contributor** | Uses the subnet/public IP from network deployment. Bastion deployment rights are not required merely to connect to the jumpbox. |
| Optional Windows jumpbox VM, NIC, managed OS disk and system-assigned identity | [`jumpbox.bicep`](../infra/modules/jumpbox.bicep) | **[Virtual Machine Contributor][compute-roles]** | This role also covers NIC creation, disk management, and existing subnet/NSG joins used here. No need to add Network Contributor *just for this jumpbox* if the network already exists and the relevant join permissions are in scope. Other modules still need Network Contributor. No VM Entra-login extension is deployed. |
| Workload data/AI/registry access and conditional jumpbox-secret group access | [`data`](../infra/modules/data.bicep), [`ai`](../infra/modules/ai.bicep), [`registry`](../infra/modules/registry.bicep), [`identity-security`](../infra/modules/identity-security.bicep) modules | **Role Based Access Control Administrator**, constrained where feasible | Assignments are at Storage account, AI account, registry and vault scopes. The complete list is in [runtime identities](#runtime-identities). |

App registration/service-principal creation and SQL user bootstrap are also required, but are **not ARM resources deployed by these modules**. Their permissions are described in the account bundles below.

## When one role can cover several services

Use this table to avoid unnecessary assignments, not to justify a broader role at a broader scope.

| Separate needs / narrower option | Covering role or bundle | What can be consolidated here | Extra access and what is still missing |
|---|---|---|---|
| Network deployment plus Private DNS Zone Contributor for DNS | **Network Contributor** at the same scopes | VNets, NSGs, peerings, IP, private endpoints, DNS zones/records/links and Bastion | All `Microsoft.Network/*`, not just DNS. Does not replace target-service approval, VM management, RBAC delegation or service-management roles. Keep DNS-only administrators on Private DNS Zone Contributor. |
| VM, NIC, disk and joins to existing subnet/NSG | **Virtual Machine Contributor** with access to those resources | The optional jumpbox and its NIC/disk; no separate NIC-management role is needed | Can manage VM extensions/run commands and other compute operations; not just VM creation. Does not create VNets, NSGs, DNS or Bastion. |
| SQL Server Contributor plus SQL DB Contributor | **SQL Server Contributor** | Server and contained database provisioning | Broader server management. **Still add SQL Security Manager for this template's Entra-only setting**; SQL grants remain separate. This is not consolidation of all SQL security permissions. |
| Workspace creation/shared keys, Application Insights, scheduled-query alert, diagnostic settings | **Monitoring Contributor** | This repository's observability creation and diagnostic writes | Wider monitoring configuration and workspace key access. An alternative is Log Analytics Contributor plus Application Insights Component Contributor, but the former also grants VM-extension and Storage-key operations. Fewer roles is not the only comparison. Monitoring Contributor does not grant all workspace lifecycle operations, such as workspace deletion. |
| Separate account-management grants for Document Intelligence and Content Understanding/model deployments | **Cognitive Services Contributor** | Same role can manage both service kinds and ARM model deployments | Assign separately on existing accounts for isolation, or once at RG for creation. RG scope covers other Cognitive Services accounts too. Does not supply token-based inference DataActions or networking/RBAC assignments. |
| Application Insights Component Contributor plus Function App management | **Website Contributor**, plus monitoring permissions needed elsewhere | Its `Microsoft.Insights/components/*` covers the Insights component when in scope, as well as `Microsoft.Web/sites/*` | Does not replace workspace creation/shared-key access, scheduled-query-rule or diagnostic permissions. Monitoring Contributor already covers the component in the full bundle. |
| Image pull and direct image push | **AcrPush** rather than AcrPull + AcrPush, in RBAC Registry Permissions mode | Direct push includes pull | Does **not** authorize ACR quick builds (`az acr build`), registry management, deletion, or ABAC-mode repository access. Do not give it to pull-only runtime identities. |
| User-assigned identity creation plus attachment | **No consolidation between Managed Identity Contributor and Managed Identity Operator** | Both are needed when the same deployer creates and attaches identities | Contributor lacks `assign/action`; Operator lacks create/write. Neither grants roles to the managed identity. |
| Container App plus managed-environment creation; Function App plus Premium plan creation | **Two roles per service pair**, as listed in the inventory | Do not mistake read/join access for create access | App Contributor does not create ACA environments; Website Contributor does not create App Service plans. |

No single recommended service-specific built-in role covers this entire repository. Contributor plus access administration reduces assignment count, but broadens access; it is not an equivalent least-privilege bundle.

## Account bundles

### Platform bootstrap and access administrator

Use a designated platform identity for subscription preparation, not the everyday publisher or workshop attendee.

1. Register the providers used by the templates. Create the workload RG before assigning RG-scoped deployer roles. Existing Entra groups for SQL administration and optional jumpbox-password retrieval must also be supplied; Bicep does not create the groups.
2. Configure Defender through [`infra/entrypoints/defender.bicep`](../infra/entrypoints/defender.bicep) using **Security Admin at subscription scope**. Review effects on unrelated resources and billing. This role is not needed on an RG-only workload deployer.
3. Grant the RG service-role bundle below and **Role Based Access Control Administrator at RG**, with delegation conditions where feasible. Restrict human administration through groups and PIM; do not give unrestricted access-delegation rights to all contributors.
4. Arrange the separate Entra app-registration and SQL bootstrap tasks below.

For a first deployment using the **unchanged root**, subscription Contributor plus RG-scoped Role Based Access Control Administrator is the broad built-in fallback. The RG must first exist for that RG-scoped assignment. Alternatively a separately approved subscription access administrator can establish access, but subscription-wide RBAC administration is not required for the workload's resource-scoped grants. Withdraw broad bootstrap elevation after provisioning; routine root redeployment requires it again.

### Delegated infrastructure deployer

For all resource-group components, assign this combined bundle at the workload RG, then use the existing resource-group entry points:

| Area | Built-in roles |
|---|---|
| Networking and jumpbox | Network Contributor; Virtual Machine Contributor only if deploying the jumpbox |
| Managed identities and vault | Managed Identity Contributor; Managed Identity Operator; Key Vault Contributor |
| Storage and eventing | Storage Account Contributor; EventGrid Contributor |
| SQL | SQL Server Contributor; SQL Security Manager |
| AI | Cognitive Services Contributor |
| Registry | Container Registry Contributor and Data Access Configuration Administrator |
| Compute | Container Apps ManagedEnvironments Contributor; Container Apps Contributor; Web Plan Contributor; Website Contributor |
| Monitoring and notification | Monitoring Contributor; Logic App Contributor |
| Runtime role assignment | Role Based Access Control Administrator, preferably constrained |

This is a complete **service-management bundle**, not a single small role. Give component maintainers only their rows plus the shared dependencies. In particular, a compute-only operator attaching existing identities needs Managed Identity Operator on those identities, not permission to create or delete all identities. For steady-state operations, narrow RG-wide grants to the resources actually being updated.

The platform must already have created the RG, registered providers, and handled subscription Defender configuration. Pass prerequisite outputs/secure values between entry points as described in [deployment](deployment.md#independent-components); the root's output wiring and callback lookup are not automatically reproduced by independently running modules. Azure role assignments made by those modules still need the delegated RBAC authority.

### Image publisher

With `deploy_infrastructure=false`, [the publishing workflow](../.github/workflows/publish-deploy.yml) discovers the registry, performs three ACR quick builds, updates the existing ACA app, changes the Function App's container settings and restarts it.

| Operation | Built-in role and scope |
|---|---|
| `az acr list -g` and registry discovery | Registry read/list at **RG scope**. The narrow service role **Container Registry Tasks Contributor at RG** supplies `registries/read` as well as quick-build rights, but applies to all registries in that RG. For a single-registry task grant, use Tasks Contributor on the registry plus **Reader at RG** for the unchanged list command; this exposes other RG resource metadata. |
| `az acr build`, build-source upload, run status and logs | **Container Registry Tasks Contributor** on the registry, or at RG as above. This is not the same as AcrPush. |
| Update existing `web` and `api` images | **Container Apps Contributor** on the Container App, with the environment read/join access used by the update operation at the environment scope |
| Set Function container configuration and restart | **Website Contributor** on the Function App, with existing plan read/join access at plan scope if required by the CLI operation |
| Preserve/attach the configured workload identities during updates | **Managed Identity Operator** on the two attached user-assigned identities; this covers identity-assignment validation if the CLI resubmits that configuration |

For the default non-ABAC registry, quick tasks have registry data access through ACR Tasks; the caller does not need an additional AcrPush grant merely to run these quick builds. This authority can execute arbitrary build instructions and write images, so treat it as effective image supply-chain access. **Direct** Docker build/push outside ACR Tasks would instead need AcrPush (and registry discovery access).

The template does not opt into **RBAC Registry + ABAC Repository Permissions**. If administrators enable that mode, [ACR's documented behavior changes][acr-roles]: quick builds require appropriate caller repository roles, such as **Container Registry Repository Writer**, and catalog-list permission where required; runtime AcrPull must be replaced with supported repository-reader grants. ABAC quick-build source authentication also needs the documented configuration. That is a coordinated deployment change, not an extra role to blindly add to this sample.

No Entra app-registration administration, SQL administrator membership, Web Plan Contributor, network-management role, or RBAC administrator role is needed for image-only publishing. With `deploy_infrastructure=true`, the same workflow identity also needs the **root** infrastructure and Entra-script permissions; the workflow currently uses one identity, not separate automatically selected bootstrap/publisher identities.

Use [OIDC federation][oidc] restricted to the intended GitHub repository/environment, with `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID`. A VNet-connected runner/private DNS is still required as described in [deployment](deployment.md#acr-publicprivate-choice). RBAC cannot make a private endpoint reachable. Permission to publish images or change app settings is effectively permission to run code as the workload identity; protect GitHub environment approvals accordingly.

For one-time [federated-credential setup][federation-setup], an **owner of the CI app registration** can establish the trust without a tenant-wide application-administrator role. Match the issuer, audience and subject to this workflow's `azure` environment (`repo:<owner>/<repo>:environment:azure`). This is separate from ownership of the application's Easy Auth registration and is not a reason to give routine publishers directory-wide administration.

### Entra application maintainer

[`register-entra-app.ps1`](../scripts/register-entra-app.ps1) lists applications by display name, creates/updates the single-tenant app, sets its identifier URI/ID-token settings, and finds/creates its service principal. [`set-entra-redirect-uris.ps1`](../scripts/set-entra-redirect-uris.ps1) updates redirect URIs and reads ACA/Function hostnames through ARM.

| Caller | Least-privilege approach and conditions |
|---|---|
| Human using `az login` | Maintain **ownership of this app**, not all apps. Tenant user settings can permit ordinary users to register apps; where registration is restricted, **Application Developer** supports creation as owner and updating owned apps. For the script's single-tenant service-principal creation, [Microsoft Graph documents Application Developer plus ownership of the backing app][graph-sp]. A directory administrator must establish ownership if a different identity created the existing app. Azure CLI's delegated Graph access and tenant consent policies must also allow the operations. |
| OIDC CI service principal running the scripts | Admin-consented Microsoft Graph **application permission `Application.ReadWrite.OwnedBy`**, with ownership of the application and any service principal being managed. This permission supports creation and tenant app/SP listing, but writes are limited to owned objects. Existing objects created by another identity need ownership established first. No client secret is required for this Graph permission when using federation. |
| Directory application administrator handling setup centrally | Can create the app/service principal, establish ownership and supply `ENTRA_CLIENT_ID`, leaving routine image publishing without directory permissions. Tenant-wide **Cloud Application Administrator**, **Application Administrator**, or `Application.ReadWrite.All` are broader alternatives for app management, not least-privilege defaults. |
| One-time administrator consenting to CI's Graph application permission | **Privileged Role Administrator** is the suitable built-in Entra role for granting Microsoft Graph application-permission consent. Application Administrator / Cloud Application Administrator do **not** suffice for Graph app-role consent. Use approved, time-bound elevation; the running CI identity does not need this directory role. See [admin-consent prerequisites][admin-consent]. |

`Application.ReadWrite.OwnedBy` is **application-only**, not a delegated permission to assign to a human. Its ability to list all apps/SPs is still tenant-wide read exposure; ownership also permits credential changes on the owned objects. Ownership of the login application does not mean ownership of the separate CI application.

The scripts/workflow comments mention broader directory prerequisites; the ownership-based options above explain the narrower route and its conditions. See [Graph permissions][graph-permissions] and [Application Developer][application-developer]. Redirect-hostname discovery additionally needs Container App/Function read permissions; Reader on those resources suffices if the maintainer has no existing management role.

### SQL bootstrap administrator

The deployment configures `SQL_ADMIN_GROUP_OBJECT_ID` as the server's Entra administrator. A human member uses Entra authentication from a private administrative host to run [`scripts/bootstrap-sql.sql`](../scripts/bootstrap-sql.sql) **against the application database**, creating users for both managed identities and granting `db_datareader`, `db_datawriter`, and `db_ddladmin`.

This group membership is separate from Azure RBAC and from the jumpbox-password group. SQL Server Contributor/SQL Security Manager do not give permission to run that SQL. Prefer the configured human administrator for this one-time step rather than making CI a permanent SQL administrator. A separately delegated SQL administrator would need database permissions to create users and change membership of the specified fixed database roles, not just a generic Azure Contributor grant.

After first schema initialization, remove **both** identities from `db_ddladmin`; the script grants it and does not automatically revoke it:

```sql
ALTER ROLE db_ddladmin DROP MEMBER [id-referralintake-func-dev];
ALTER ROLE db_ddladmin DROP MEMBER [id-referralintake-aca-dev];
```

Substitute the actual names for other workloads/environments. Retain reader/writer for application operation; separately authorize future schema changes. These fixed roles are database-wide, not table-level least privilege.

`CREATE USER ... FROM EXTERNAL PROVIDER` also performs directory lookup. Human and unattended service-principal paths differ: [SQL's configuration guidance][sql-configuration] describes on-behalf-of-user Graph access; [service-principal bootstrap][sql-sp] can require a SQL server identity with Graph lookup permissions. This template does **not** provision that server identity or those Graph grants. Do not assume giving the CI principal SQL admin membership alone enables unattended bootstrap, and do not grant tenant Directory Readers to every deployer.

## Runtime identities

These are **current deployed grants**, not proposed permissions for the human deployer. The deployer needs authority to create the assignments; it does not need these data roles on its own account.

| Principal | Current scope | Role / ID | Purpose and limit |
|---|---|---|---|
| Function and ACA user-assigned identities | Storage account | **Storage Blob Data Contributor** / `ba92f5b4-2d11-453d-a403-e96b0029c9fe` | Upload, read, move/delete pipeline documents across the four containers. Not just access to `incoming`. |
| Function and ACA identities | Storage account | **Storage Queue Data Contributor** / `974c5e8b-45b9-4653-ba55-5f855dd0fb88` | Function queue processing/poison handling and ACA diagnostics. Full queue data access, not just peek or send. |
| Event Grid system-topic system-assigned identity | Storage account | **Storage Queue Data Message Sender** / `c6a89b2d-59bc-44d0-9896-0f6e12d7b80a` | Enqueue BlobCreated notifications. Sender-only operations, but the current account scope is broader than one queue. |
| Function and ACA identities | Each of the two AI accounts | **Cognitive Services User** / `a97b65f3-24c7-4388-baec-2e87135dc908` | Broad `Microsoft.CognitiveServices/*` DataActions support token-based AI use, including Content Understanding analyzer/default setup in the API. Not merely a read-only inference role. |
| Function and ACA identities | ACR | **AcrPull** / `7f951dda-4ed3-4680-a7ca-43fe172d538d` | Pull the function/web/API images in the default RBAC registry mode. Does not enforce image signing or approval. |
| `JUMPBOX_ADMIN_GROUP_OBJECT_ID` (group or user) | Key Vault | **Key Vault Secrets User** / `4633458b-17de-408a-b874-0445c86b69e6` | Read the password secret; grants secret reads throughout this vault. Only assigned when password storage is enabled and this object ID is nonempty. |
| Function and ACA identities | Application SQL database | `db_datareader`, `db_datawriter`, initially `db_ddladmin` | SQL grants from the manual bootstrap script, **not Azure RBAC**. Remove DDL access after initialization. |

The Logic App and optional jumpbox have system-assigned identities but **no Azure role assignments to them are declared here**. The API/Function invokes the Logic App using its SAS-bearing callback URL, not an RBAC grant to the Logic App identity. Future connectors need their own authentication/consent.

These grants are not a claim of absolute runtime minimum privilege. Potential follow-up changes include queue-scoping the Event Grid sender, narrowing participant secret access, and reducing ACA queue/AI privileges only after preserving analyzer initialization and diagnostics. Such changes require template/application validation and are not implemented by this documentation.

## Participants and operators

Give participants permissions for their actual activity, not the deployment bundle. Azure roles do not supply private connectivity, browser access, or OS/SQL login.

| Activity | Minimum suitable access for that activity | What not to grant / important boundary |
|---|---|---|
| Open the web app, upload sample files, review/delete referrals through the UI | Tenant Entra sign-in accepted by the app, and private network/browser reachability | **No Azure resource role is needed just to use the UI.** Current Easy Auth/API checks authenticate users but do not implement distinct reviewer/admin roles or a group allowlist. Enterprise-app assignment/tenant policies can further restrict sign-in if configured outside this template. |
| Connect to the jumpbox using portal Bastion/RDP | **Reader** on VM, NIC and Bastion, plus valid OS credentials; Reader on the target VNet when connecting through peering | Basic Bastion supports browser connections; native-client access needs a different SKU/configuration. [Bastion prerequisites][bastion-access] distinguish resource read rights from OS login. VM Contributor is unnecessary merely to connect. |
| Retrieve `jumpbox-admin-password` | **Key Vault Secrets User** on that secret, or existing vault-scope grant, plus private vault reachability | The template grants at **vault**, not secret, scope. Membership in the password group does not itself give Bastion Reader or SQL administrator rights. Local password login is configured; VM Entra-login roles alone will not configure it. |
| Reset the VM password and rotate its vault copy | **Virtual Machine Contributor** on the VM plus **Key Vault Secrets Officer** on the vault/secret being maintained | Two independent updates: resetting VM credentials does not update the secret. Secrets User is read-only; Key Vault Contributor is not authorization for data-plane `az keyvault secret set`. |
| Drop a document directly into `incoming` using CLI/AzCopy | **Storage Blob Data Contributor** on the `incoming` container; private Blob endpoint access | Use Entra/OAuth (for example `--auth-mode login`), not keys. This built-in role also allows read/delete; it is not write-only. Other container access is unnecessary for upload-only participants. |
| Inspect blobs across pipeline stages | **Storage Blob Data Reader** on the relevant containers | No need for Storage Account Contributor. Portal resource discovery may additionally need ARM Reader; a known endpoint/container avoids broad management grants. |
| Inspect queue depth and peek messages | **Storage Queue Data Reader** on the jobs/poison queues | Does not authorize deleting or replaying messages. Add a deliberately scoped message role only if remediation is part of the job. |
| Query pipeline logs | **Log Analytics Reader** on the workspace | Includes query rights; use workspace scope, not subscription-wide monitoring administration. Logs can contain application data. |
| Read Event Grid delivery metrics/resource configuration | **Reader** on the system topic and other resources being inspected | Not EventGrid Contributor unless changing eventing configuration. |
| Run `az containerapp exec` and the documented diagnostics | **Container Apps Operator** on the app, with environment read access as needed | Operator includes exec/logstream/debug DataActions. Reader is insufficient. Diagnostics run as the ACA identity and can upload/delete documents, change analyzer configuration and write SQL; do not classify shell access as read-only support access. |
| Administer SQL or inspect application data directly | Configured Entra SQL admin membership for bootstrap, or a separately created database user with task-specific SQL grants, plus private SQL reachability | Azure Reader/SQL Server Contributor are not database users. Routine reviewers should use the UI rather than share the SQL admin group. |
| Change notification workflow/add connectors | **Logic App Contributor** on the workflow; connector-specific authorization/consent | Not required to review referrals. Workflow access may expose run payloads and callback credentials. |

## Before assigning access

Review the role's actual actions and existing inherited grants, not just its name. For example, these read-only commands show the SQL security exclusion and a principal's RG assignments:

```powershell
az role definition list --name 'SQL Server Contributor' `
  --query '[0].{role:roleName,id:name,permissions:permissions}' -o json

az role assignment list --assignee-object-id '<principal-object-id>' `
  --scope '/subscriptions/<subscription-id>/resourceGroups/rg-referralintake' `
  --include-inherited --all -o table
```

The assignment list is an audit aid, not a complete effective-access calculation: review group membership, PIM activation, resource-scoped assignments, conditions and deny assignments too. Use stable role IDs for automated assignments and verify the tenant/subscription and principal **object ID**, not just the application/client ID.

Use the [deployment what-if procedure](deployment.md#root-deployment-and-what-if) with the intended identity and deployment path. Default provider validation needs deployment/write permissions; a read-only or template-only validation is not proof that an identity can deploy. A successful what-if is also not an end-to-end data-plane or private-network test.

This guide was checked against repository declarations and Microsoft Learn role definitions, not a live deployment of every role combination. Tenant policy, consent restrictions, deny assignments, role propagation, quota/model availability and private DNS/connectivity can still block a correctly scoped role bundle. No Azure deployments or permission changes are performed by this guide.

## Microsoft Learn references

- [Azure RBAC best practices][rbac-practices], [built-in role catalog][roles], and [constrained role-assignment delegation][delegation].
- [Bicep deployment/what-if permissions][what-if] and [resource-provider registration][providers].
- [Networking][network-roles], [compute][compute-roles], [managed identity][identity-roles], [security][security-roles], [Storage][storage-roles], [SQL][database-roles], [AI][ai-roles], [containers][container-roles], [web][web-roles], [integration][integration-roles], and [monitoring][monitor-roles] built-in role definitions.
- [ACR role and permission-mode reference][acr-roles], [GitHub OIDC federation][oidc], [Key Vault RBAC][vault-rbac], and [ARM secret resource][arm-secret].
- [Graph application permissions][graph-permissions], [service-principal creation permissions][graph-sp], [Entra Application Developer][application-developer], [admin consent][admin-consent], and [federated-credential setup][federation-setup].
- [SQL Entra-only authentication][sql-entra-only], [Entra database-user configuration][sql-configuration], [SQL service-principal bootstrap][sql-sp], and [Bastion RDP prerequisites][bastion-access].

[rbac-practices]: https://learn.microsoft.com/azure/role-based-access-control/best-practices
[roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
[delegation]: https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-overview
[what-if]: https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if
[providers]: https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types
[network-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/networking
[compute-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/compute
[identity-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/identity
[security-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/security
[storage-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/storage
[database-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/databases
[ai-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning
[container-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/containers
[web-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/web-and-mobile
[integration-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/integration
[monitor-roles]: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/monitor
[acr-roles]: https://learn.microsoft.com/azure/container-registry/container-registry-rbac-built-in-roles-directory-reference
[oidc]: https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect
[vault-rbac]: https://learn.microsoft.com/azure/key-vault/general/rbac-guide
[arm-secret]: https://learn.microsoft.com/azure/templates/microsoft.keyvault/vaults/secrets
[graph-permissions]: https://learn.microsoft.com/graph/permissions-reference#applicationreadwriteownedby
[graph-sp]: https://learn.microsoft.com/graph/api/serviceprincipal-post-serviceprincipals
[application-developer]: https://learn.microsoft.com/entra/identity/role-based-access-control/permissions-reference#application-developer
[admin-consent]: https://learn.microsoft.com/entra/identity/enterprise-apps/grant-admin-consent
[federation-setup]: https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust
[sql-entra-only]: https://learn.microsoft.com/azure/azure-sql/database/authentication-azure-ad-only-authentication
[sql-configuration]: https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-configure
[sql-sp]: https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial
[bastion-access]: https://learn.microsoft.com/azure/bastion/bastion-connect-vm-rdp-windows
