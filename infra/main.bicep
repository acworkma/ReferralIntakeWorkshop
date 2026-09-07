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
@description('Object ID of the Entra group granted read access to the jumpbox admin password Key Vault secret.')
param jumpboxAdminGroupObjectId string
@secure()
param jumpboxAdminPassword string
@description('Premium ACR may be reachable publicly for hosted CI. Disable after configuring a private runner.')
param acrPublicNetworkAccess bool = true
param deployJumpbox bool = true
@description('Container Apps environment default domain. Set after initial deployment to provision private ingress DNS.')
param containerAppsDefaultDomain string = ''
@description('Image tag to deploy for the web, api, and function images. Leave empty on a first deployment: the template then uses public placeholder images so it can stand up before any image exists.')
param imageTag string = ''
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
    jumpboxAdminPassword: jumpboxAdminPassword
    jumpboxAdminGroupObjectId: jumpboxAdminGroupObjectId
    storeJumpboxPassword: deployJumpbox
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
    functionPrincipalId: identity.outputs.functionPrincipalId
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
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
    tags: tags
  }
}

// Reading the callback URL here keeps the SAS-signed trigger address out of the
// template's own outputs. It reaches the function and the API as a secure parameter.
var notificationWorkflowTriggerId = resourceId(
  subscription().subscriptionId,
  resourceGroupName,
  'Microsoft.Logic/workflows/triggers',
  'logic-${workloadName}-notification-${environmentName}',
  'manual'
)

module compute 'modules/compute.bicep' = {
  scope: resourceGroup
  name: 'compute'
  dependsOn: [integration]
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
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
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
    imageTag: imageTag
    logicAppUrl: listCallbackUrl(notificationWorkflowTriggerId, '2019-05-01').value
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

// Deployed last on purpose. See eventing.bicep for why.
module eventing 'modules/eventing.bicep' = {
  scope: resourceGroup
  name: 'eventing'
  dependsOn: [compute, integration, bastion]
  params: {
    systemTopicName: data.outputs.eventGridSystemTopicName
    storageAccountId: data.outputs.storageAccountId
    incomingContainer: data.outputs.incomingContainer
    jobsQueueName: data.outputs.jobsQueueName
  }
}

output resourceGroupName string = resourceGroup.name
output webFqdn string = compute.outputs.webFqdn
output containerAppsDefaultDomain string = compute.outputs.containerAppsDefaultDomain
output functionHostName string = compute.outputs.functionHostName
output acrLoginServer string = registry.outputs.loginServer
output keyVaultName string = identity.outputs.keyVaultName
output localMockIdentityEnabled bool = false
