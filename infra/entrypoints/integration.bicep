targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param storageAccountId string
param logAnalyticsWorkspaceId string
param tags object = { managedBy: 'bicep' }

module component '../modules/integration.bicep' = {
  name: 'integration'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    storageAccountId: storageAccountId
    logAnalyticsWorkspaceId: logAnalyticsWorkspaceId
    tags: tags
  }
}
