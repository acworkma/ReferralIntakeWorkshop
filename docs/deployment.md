# Deployment

## Prerequisites

- Azure CLI with current Bicep CLI (`az bicep upgrade`)
- Owner or User Access Administrator plus Contributor at the target subscription
- A directory-level Entra role capable of managing app registrations (e.g. **Application Administrator** or **Cloud Application Administrator**, or the Microsoft Graph `Application.ReadWrite.All` permission) for whichever identity runs `scripts/register-entra-app.ps1`/`scripts/set-entra-redirect-uris.ps1` — a human via `az login`, or the CI OIDC service principal. This is a directory permission, distinct from Azure RBAC, and can't be granted through Bicep/ARM.
- Entra group for SQL administration
- Private DNS/network reachability for administration and a VNet-connected CI runner

Register providers once:

```powershell
$providers = 'Microsoft.App','Microsoft.Web','Microsoft.Storage','Microsoft.Sql','Microsoft.CognitiveServices','Microsoft.KeyVault','Microsoft.Network','Microsoft.OperationalInsights','Microsoft.Insights','Microsoft.Security','Microsoft.ContainerRegistry','Microsoft.Logic','Microsoft.Compute'
$providers | ForEach-Object { az provider register --namespace $_ }
```

Create the Microsoft Entra app registration used by Container Apps/Function "Easy Auth" (`scripts/register-entra-app.ps1` finds-or-creates it by a stable name and prints the client ID as its only pipeline output):

```powershell
$env:ENTRA_CLIENT_ID = .\scripts\register-entra-app.ps1
```

Set the remaining four environment variables referenced by `infra/main.bicepparam`: `AZURE_UNIQUE_SUFFIX`, `SQL_ADMIN_GROUP_OBJECT_ID`, `JUMPBOX_ADMIN_GROUP_OBJECT_ID`, and `JUMPBOX_ADMIN_PASSWORD`. Keep the password in CI environment secrets, never in a checked-in parameter file.

## Root deployment and what-if

```powershell
az deployment sub what-if `
  --name referral-whatif `
  --location eastus2 `
  --template-file infra\main.bicep `
  --parameters infra\main.bicepparam

az deployment sub create `
  --name referral-deploy `
  --location eastus2 `
  --template-file infra\main.bicep `
  --parameters infra\main.bicepparam
```

The root creates `rg-referralintake`. It intentionally deploys Microsoft sample placeholders first because a new ACR is empty. After the root deployment completes, patch the app registration's redirect URIs now that the Container Apps/Function hostnames exist:

```powershell
.\scripts\set-entra-redirect-uris.ps1
```

Publish `web` and `api` with `.github/workflows/publish-deploy.yml`; that workflow rolls the two ACA containers and deploys the Function package. Connect through Azure Bastion (Basic SKU) to `vm-referralintake-jump-dev` for private administration tasks (including `scripts/bootstrap-sql.sql`), then restart the API revision so SQLAlchemy creates the schema.

## Independent components

Every component has a resource-group entry point under `infra/entrypoints`; Defender remains subscription-scoped. Pass outputs from prerequisites explicitly:

```powershell
az deployment group what-if -g rg-referralintake `
  --template-file infra\entrypoints\network.bicep
az deployment group create -g rg-referralintake `
  --template-file infra\entrypoints\network.bicep

az deployment group create -g rg-referralintake `
  --template-file infra\entrypoints\registry.bicep `
  --parameters uniqueSuffix=abc123 `
    privateEndpointSubnetId='<network-output>' `
    acrPrivateDnsZoneId='<network-output>' `
    containerAppsPrincipalId='<identity-output>'
```

Use the same `az deployment group what-if/create` pattern for `observability`, `identity-security`, `data`, `ai`, `compute`, `integration`, `bastion`, and `jumpbox`. Deploy in that order (`bastion` and `jumpbox` both depend on `network`'s hub VNet/subnet outputs and can be deployed in either order relative to each other). Deploy Defender with `az deployment sub what-if/create --location eastus2 --template-file infra\entrypoints\defender.bicep`.

## ACR public/private choice

`acrPublicNetworkAccess=true` is the default so hosted build systems can push during bootstrap. Premium ACR still has a private endpoint, admin credentials are disabled, and anonymous pull is disabled. Public access expands the network surface even though Entra/RBAC still protects it.

After deploying a private runner with private DNS reachability, set `acrPublicNetworkAccess=false` and rerun what-if/deploy. Hosted runners cannot push to a private-only ACR. ACR Tasks (`az acr build`) may be another option subject to tenant policy. See [ACR private link](https://learn.microsoft.com/azure/container-registry/container-registry-private-link) and [ACR network rules](https://learn.microsoft.com/azure/container-registry/container-registry-access-selected-networks).

## CI identity

Configure GitHub environment variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` for workload identity federation—no client secret. Grant the deployment identity least privilege at the subscription (Azure RBAC), plus the directory-level app-registration role described in Prerequisites if the CI pipeline runs `scripts/register-entra-app.ps1`/`scripts/set-entra-redirect-uris.ps1` (see `.github/workflows/publish-deploy.yml`). See [Azure Login with OIDC](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) and [Bicep what-if](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if).
