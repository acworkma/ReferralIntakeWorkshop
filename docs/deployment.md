# Deployment

## Prerequisites

- Azure CLI with current Bicep CLI (`az bicep upgrade`)
- Owner or User Access Administrator plus Contributor at the target subscription
- Microsoft Entra app registration with redirect URI `https://<private-app-fqdn>/.auth/login/aad/callback`
- Entra groups for SQL administration and JIT requesters
- Private DNS/network reachability for administration and a VNet-connected CI runner

Register providers once:

```powershell
$providers = 'Microsoft.App','Microsoft.Web','Microsoft.Storage','Microsoft.Sql','Microsoft.CognitiveServices','Microsoft.KeyVault','Microsoft.Network','Microsoft.OperationalInsights','Microsoft.Insights','Microsoft.Security','Microsoft.ContainerRegistry','Microsoft.Logic','Microsoft.Compute'
$providers | ForEach-Object { az provider register --namespace $_ }
```

Set the five environment variables referenced by `infra/main.bicepparam`: `AZURE_UNIQUE_SUFFIX`, `ENTRA_CLIENT_ID`, `SQL_ADMIN_GROUP_OBJECT_ID`, `JUMPBOX_ADMIN_GROUP_OBJECT_ID`, and `JUMPBOX_ADMIN_PASSWORD`. Keep the password in CI environment secrets, never in a checked-in parameter file.

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

The root creates `rg-referralintake`. It intentionally deploys Microsoft sample placeholders first because a new ACR is empty. Publish `web` and `api` with `.github/workflows/publish-deploy.yml`; that workflow rolls the two ACA containers and deploys the Function package. Run `scripts/bootstrap-sql.sql` from the JIT host, then restart the API revision so SQLAlchemy creates the schema.

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

Use the same `az deployment group what-if/create` pattern for `observability`, `identity-security`, `data`, `ai`, `compute`, `integration`, and `jumpbox`. Deploy in that order. Deploy Defender with `az deployment sub what-if/create --location eastus2 --template-file infra\entrypoints\defender.bicep`.

## ACR public/private choice

`acrPublicNetworkAccess=true` is the default so hosted build systems can push during bootstrap. Premium ACR still has a private endpoint, admin credentials are disabled, and anonymous pull is disabled. Public access expands the network surface even though Entra/RBAC still protects it.

After deploying a private runner with private DNS reachability, set `acrPublicNetworkAccess=false` and rerun what-if/deploy. Hosted runners cannot push to a private-only ACR. ACR Tasks (`az acr build`) may be another option subject to tenant policy. See [ACR private link](https://learn.microsoft.com/azure/container-registry/container-registry-private-link) and [ACR network rules](https://learn.microsoft.com/azure/container-registry/container-registry-access-selected-networks).

## CI identity

Configure GitHub environment variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` for workload identity federation—no client secret. Grant the deployment identity least privilege. See [Azure Login with OIDC](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) and [Bicep what-if](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if).
