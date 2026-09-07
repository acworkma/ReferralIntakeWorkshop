targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param entraClientId string
param tenantId string = tenant().tenantId
param acaSubnetId string
param hubVnetId string
param spokeVnetId string
param containerAppsDefaultDomain string = ''
param functionSubnetId string
param privateEndpointSubnetId string
param sitesPrivateDnsZoneId string
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string
@secure()
param appInsightsConnectionString string
param containerAppsIdentityId string
param containerAppsIdentityClientId string
param functionIdentityId string
param functionIdentityClientId string
param storageAccountName string
param sqlServerFqdn string
param sqlDatabaseName string
param documentIntelligenceEndpoint string
param contentUnderstandingEndpoint string
param acrLoginServer string
param imageTag string = ''
param logAnalyticsWorkspaceId string
@secure()
param logicAppUrl string = ''
param tags object = { managedBy: 'bicep' }

module component '../modules/compute.bicep' = {
  name: 'compute'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    entraClientId: entraClientId
    tenantId: tenantId
    acaSubnetId: acaSubnetId
    hubVnetId: hubVnetId
    spokeVnetId: spokeVnetId
    containerAppsDefaultDomain: containerAppsDefaultDomain
    functionSubnetId: functionSubnetId
    privateEndpointSubnetId: privateEndpointSubnetId
    sitesPrivateDnsZoneId: sitesPrivateDnsZoneId
    logAnalyticsCustomerId: logAnalyticsCustomerId
    logAnalyticsSharedKey: logAnalyticsSharedKey
    appInsightsConnectionString: appInsightsConnectionString
    containerAppsIdentityId: containerAppsIdentityId
    containerAppsIdentityClientId: containerAppsIdentityClientId
    functionIdentityId: functionIdentityId
    functionIdentityClientId: functionIdentityClientId
    storageAccountName: storageAccountName
    sqlServerFqdn: sqlServerFqdn
    sqlDatabaseName: sqlDatabaseName
    documentIntelligenceEndpoint: documentIntelligenceEndpoint
    contentUnderstandingEndpoint: contentUnderstandingEndpoint
    acrLoginServer: acrLoginServer
    imageTag: imageTag
    logAnalyticsWorkspaceId: logAnalyticsWorkspaceId
    logicAppUrl: logicAppUrl
    tags: tags
  }
}

output webFqdn string = component.outputs.webFqdn
output containerAppsDefaultDomain string = component.outputs.containerAppsDefaultDomain
