targetScope = 'subscription'

@description('Resource group for the reference deployment.')
param resourceGroupName string = 'rg-referralintake'
param location string = 'eastus2'
@description('SQL region, used when SQL provisioning is restricted in the primary region.')
param sqlLocation string = 'eastus'
@description('US fallback for services not available in the primary region.')
param aiFallbackLocation string = 'westus3'
param workloadName string = 'referralintake'
@allowed(['dev', 'test', 'prod'])
param environmentName string = 'dev'
@description('Stable lowercase suffix, 3-8 alphanumeric characters, used by globally unique resources.')
param uniqueSuffix string
@description('Microsoft Entra application client ID used by ACA and Functions authentication.')
param entraClientId string
@description('Microsoft Entra tenant ID.')
param tenantId string = tenant().tenantId
@description('Object ID of the Entra group that administers Azure SQL.')
param sqlAdminGroupObjectId string
@description('Object ID retained for backward compatibility; JIT is no longer deployed.')
param jumpboxAdminGroupObjectId string
@secure()
param jumpboxAdminPassword string
@description('Premium ACR may be reachable publicly for hosted CI. Disable after configuring a private runner.')
param acrPublicNetworkAccess bool = true
param deployJumpbox bool = true
@description('Container Apps environment default domain. Set after initial deployment to provision private ingress DNS.')
param containerAppsDefaultDomain string = ''
param tags object = {
  workload: workloadName
  environment: environmentName
  managedBy: 'bicep'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module network 'modules/network.bicep' = {
  scope: resourceGroup
  name: 'network'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    tags: tags
  }
}

module observability 'modules/observability.bicep' = {
  scope: resourceGroup
  name: 'observability'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    tags: tags
  }
}

module identity 'modules/identity-security.bicep' = {
  scope: resourceGroup
  name: 'identity-security'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    privateEndpointSubnetId: network.outputs.privateEndpointSubnetId
    keyVaultPrivateDnsZoneId: network.outputs.keyVaultPrivateDnsZoneId
    tags: tags
  }
}

module data 'modules/data.bicep' = {
  scope: resourceGroup
  name: 'data'
  params: {
    location: location
    sqlLocation: sqlLocation
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    sqlAdminGroupObjectId: sqlAdminGroupObjectId
    tenantId: tenantId
    privateEndpointSubnetId: network.outputs.privateEndpointSubnetId
    blobPrivateDnsZoneId: network.outputs.blobPrivateDnsZoneId
    queuePrivateDnsZoneId: network.outputs.queuePrivateDnsZoneId
    sqlPrivateDnsZoneId: network.outputs.sqlPrivateDnsZoneId
    functionPrincipalId: identity.outputs.functionPrincipalId
    containerAppsPrincipalId: identity.outputs.containerAppsPrincipalId
    tags: tags
  }
}

module ai 'modules/ai.bicep' = {
  scope: resourceGroup
  name: 'ai'
  params: {
    location: location
    aiFallbackLocation: aiFallbackLocation
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    privateEndpointSubnetId: network.outputs.privateEndpointSubnetId
    cognitivePrivateDnsZoneId: network.outputs.cognitivePrivateDnsZoneId
    functionPrincipalId: identity.outputs.functionPrincipalId
    containerAppsPrincipalId: identity.outputs.containerAppsPrincipalId
    tags: tags
  }
}

module registry 'modules/registry.bicep' = {
  scope: resourceGroup
  name: 'registry'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    publicNetworkAccess: acrPublicNetworkAccess
    privateEndpointSubnetId: network.outputs.privateEndpointSubnetId
    acrPrivateDnsZoneId: network.outputs.acrPrivateDnsZoneId
    containerAppsPrincipalId: identity.outputs.containerAppsPrincipalId
    tags: tags
  }
}

module compute 'modules/compute.bicep' = {
  scope: resourceGroup
  name: 'compute'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    entraClientId: entraClientId
    tenantId: tenantId
    acaSubnetId: network.outputs.acaSubnetId
    hubVnetId: network.outputs.hubVnetId
    spokeVnetId: network.outputs.spokeVnetId
    containerAppsDefaultDomain: containerAppsDefaultDomain
    functionSubnetId: network.outputs.functionSubnetId
    privateEndpointSubnetId: network.outputs.privateEndpointSubnetId
    sitesPrivateDnsZoneId: network.outputs.sitesPrivateDnsZoneId
    logAnalyticsCustomerId: observability.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: observability.outputs.logAnalyticsSharedKey
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    containerAppsIdentityId: identity.outputs.containerAppsIdentityId
    containerAppsIdentityClientId: identity.outputs.containerAppsClientId
    functionIdentityId: identity.outputs.functionIdentityId
    functionIdentityClientId: identity.outputs.functionClientId
    storageAccountName: data.outputs.storageAccountName
    sqlServerFqdn: data.outputs.sqlServerFqdn
    sqlDatabaseName: data.outputs.sqlDatabaseName
    documentIntelligenceEndpoint: ai.outputs.documentIntelligenceEndpoint
    contentUnderstandingEndpoint: ai.outputs.contentUnderstandingEndpoint
    acrLoginServer: registry.outputs.loginServer
    tags: tags
  }
}

module integration 'modules/integration.bicep' = {
  scope: resourceGroup
  name: 'integration'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    storageAccountId: data.outputs.storageAccountId
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
    tags: tags
  }
}

module jumpbox 'modules/jumpbox.bicep' = if (deployJumpbox) {
  scope: resourceGroup
  name: 'jumpbox'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    jumpboxSubnetId: network.outputs.jumpboxSubnetId
    adminPassword: jumpboxAdminPassword
    tags: tags
  }
}

module bastion 'modules/bastion.bicep' = {
  scope: resourceGroup
  name: 'bastion'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    bastionSubnetId: network.outputs.bastionSubnetId
    bastionPublicIpId: network.outputs.bastionPublicIpId
    tags: tags
  }
}

module security 'modules/defender.bicep' = {
  name: 'defender'
  params: {}
}

output resourceGroupName string = resourceGroup.name
output webFqdn string = compute.outputs.webFqdn
output containerAppsDefaultDomain string = compute.outputs.containerAppsDefaultDomain
output functionHostName string = compute.outputs.functionHostName
output acrLoginServer string = registry.outputs.loginServer
output localMockIdentityEnabled bool = false
